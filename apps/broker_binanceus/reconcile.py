from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog

from core.broker import BalanceSnapshot, BrokerOrderAck, BrokerOrderUpdate
from core.contracts import FillEvent


class BusProto(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None: ...


class ReconcileBrokerProto(Protocol):
    def fetch_open_orders(self, symbol: str | None = None) -> list[BrokerOrderUpdate]: ...

    def fetch_balances(self) -> list[BalanceSnapshot]: ...

    def fetch_trades(self, since: int | None = None) -> list[dict[str, Any]]: ...

    def find_order_by_client_id(self, client_order_id: str) -> BrokerOrderAck | None: ...


InflightProvider = Callable[[], Awaitable[set[str]]]


@dataclass(frozen=True)
class TradeWatermark:
    timestamp_ms: int
    trade_id: str

    @property
    def key(self) -> tuple[int, str]:
        return (self.timestamp_ms, self.trade_id)

    @classmethod
    def empty(cls) -> TradeWatermark:
        return cls(timestamp_ms=-1, trade_id="")


class ReconcileService:
    def __init__(
        self,
        broker: ReconcileBrokerProto,
        bus: BusProto,
        *,
        get_inflight: InflightProvider,
        fills_topic: str,
        balance_topic: str,
        state_path: Path,
        symbols: Iterable[str],
        interval_s: float = 30.0,
    ) -> None:
        self._broker = broker
        self._bus = bus
        self._get_inflight = get_inflight
        self._fills_topic = fills_topic
        self._balance_topic = balance_topic
        self._state_path = state_path
        self._interval_s = interval_s
        self._symbols = {symbol for symbol in symbols}
        self._log = structlog.get_logger("broker.binanceus.reconcile")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._watermark = self._load_watermark()

    async def run(self) -> None:
        while True:
            await self.reconcile_once()
            await asyncio.sleep(self._interval_s)

    async def reconcile_once(self) -> None:
        inflight = await self._get_inflight()
        open_orders = self._safe_fetch_open_orders()
        self._verify_inflight(open_orders, inflight)
        new_trades = self._collect_new_trades()
        if new_trades:
            await self._publish_fills(new_trades)
            self._advance_watermark(new_trades[-1])
        await self._publish_balances()

    def _safe_fetch_open_orders(self) -> list[BrokerOrderUpdate]:
        try:
            return self._broker.fetch_open_orders()
        except Exception as exc:  # pragma: no cover - logging path
            self._log.warning("reconcile_open_orders_failed", error=str(exc))
            return []

    def _verify_inflight(self, open_orders: list[BrokerOrderUpdate], inflight: set[str]) -> None:
        if not inflight:
            return
        open_client_ids = {
            str(order.raw.get("clientOrderId"))
            for order in open_orders
            if order.raw.get("clientOrderId")
        }
        missing: list[str] = []
        for client_id in sorted(inflight):
            if client_id in open_client_ids:
                continue
            order = self._broker.find_order_by_client_id(client_id)
            if order is not None:
                continue
            missing.append(client_id)
        if missing:
            self._log.warning("reconcile_missing_orders", client_order_ids=missing)

    def _collect_new_trades(self) -> list[dict[str, Any]]:
        since = self._watermark.timestamp_ms if self._watermark.timestamp_ms >= 0 else None
        try:
            trades = self._broker.fetch_trades(since=since)
        except Exception as exc:  # pragma: no cover - logging path
            self._log.warning("reconcile_trades_failed", error=str(exc))
            return []
        filtered: list[tuple[tuple[int, str], dict[str, Any]]] = []
        for trade in trades:
            key = self._trade_key(trade)
            if key <= self._watermark.key:
                continue
            symbol = str(trade.get("symbol") or "")
            if self._symbols and symbol not in self._symbols:
                continue
            filtered.append((key, trade))
        filtered.sort(key=lambda item: item[0])
        return [item[1] for item in filtered]

    async def _publish_fills(self, trades: list[dict[str, Any]]) -> None:
        for trade in trades:
            fill = self._trade_to_fill(trade)
            await self._bus.publish_json(self._fills_topic, asdict(fill))

    async def _publish_balances(self) -> None:
        try:
            balances = self._broker.fetch_balances()
        except Exception as exc:  # pragma: no cover - logging path
            self._log.warning("reconcile_balances_failed", error=str(exc))
            return
        for snapshot in balances:
            await self._bus.publish_json(self._balance_topic, asdict(snapshot))

    def _advance_watermark(self, trade: dict[str, Any]) -> None:
        key = self._trade_key(trade)
        self._watermark = TradeWatermark(timestamp_ms=key[0], trade_id=key[1])
        payload = {
            "timestamp_ms": self._watermark.timestamp_ms,
            "trade_id": self._watermark.trade_id,
        }
        self._state_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    def _load_watermark(self) -> TradeWatermark:
        if not self._state_path.exists():
            return TradeWatermark.empty()
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - fallback for malformed state
            return TradeWatermark.empty()
        timestamp_ms = self._as_int(raw.get("timestamp_ms"), default=-1)
        trade_id = str(raw.get("trade_id") or "")
        return TradeWatermark(timestamp_ms=timestamp_ms, trade_id=trade_id)

    def _trade_to_fill(self, trade: dict[str, Any]) -> FillEvent:
        order_id = self._extract_order_id(trade)
        symbol = str(trade.get("symbol") or "")
        side = str(trade.get("side") or "buy")
        qty = float(trade.get("amount") or trade.get("filled") or 0.0)
        price = float(trade.get("price") or trade.get("cost") or 0.0)
        ts_ms = self._as_int(trade.get("timestamp"), default=int(time.time() * 1000))
        fee = self._extract_fee(trade.get("fee"))
        meta = {
            "exchange_trade_id": str(trade.get("id") or ""),
        }
        return FillEvent(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            ts_fill_ns=ts_ms * 1_000_000,
            fee=fee,
            meta=meta,
        )

    @staticmethod
    def _trade_key(trade: dict[str, Any]) -> tuple[int, str]:
        timestamp_ms = ReconcileService._as_int(trade.get("timestamp"), default=0)
        trade_id_raw = trade.get("id")
        trade_id = str(trade_id_raw or "")
        return (timestamp_ms, trade_id)

    @staticmethod
    def _extract_order_id(trade: dict[str, Any]) -> str:
        order_id = trade.get("order")
        if order_id:
            return str(order_id)
        info = trade.get("info")
        if isinstance(info, dict):
            embedded = info.get("orderId") or info.get("clientOrderId")
            if embedded:
                return str(embedded)
        trade_id = trade.get("id")
        return str(trade_id or "")

    @staticmethod
    def _extract_fee(fee: Any) -> float:
        if isinstance(fee, dict):
            cost = fee.get("cost")
            if cost is not None:
                try:
                    return float(cost)
                except (TypeError, ValueError):
                    return 0.0
        if fee is None:
            return 0.0
        try:
            return float(fee)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _as_int(value: Any, *, default: int) -> int:
        if isinstance(value, bool):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
