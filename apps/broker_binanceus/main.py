from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import structlog

from apps.broker_binanceus.adapter import BinanceUSBroker
from apps.broker_binanceus.reconcile import ReconcileService
from core import kill_switch
from core.broker import BrokerOrderAck, BrokerOrderReq, map_intent_to_broker
from core.bus import Bus
from core.config import Config, load_config
from core.contracts import OrderIntent
from core.journal import NdjsonJournal
from core.logging import setup_json_logging

BALANCE_TOPIC = "broker.balances"
OPEN_ORDERS_TOPIC = "broker.orders"
ECHO_TOPIC = "broker.echo"
ACK_TOPIC = "broker.acks"
CANCEL_TOPIC = "orders.cancel"
RISK_DECISIONS_TOPIC = "risk.decisions"
TERMINAL_STATUSES = {"FILLED", "CANCELED", "REJECTED"}
LIVE_MICRO_CAP_USD = 10.0


class BusProto(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


class BrokerPlaceProto(Protocol):
    _read_only: bool

    def place(self, req: BrokerOrderReq) -> BrokerOrderAck: ...


def _binance_secrets(config: Config) -> tuple[str | None, str | None]:
    api_keys = config.secrets.api_keys
    if not api_keys:
        return None, None
    binance_cfg = getattr(api_keys, "binanceus", None)
    if binance_cfg is None:
        return None, None
    if isinstance(binance_cfg, dict):
        return binance_cfg.get("key"), binance_cfg.get("secret")
    return binance_cfg.key, binance_cfg.secret


async def _periodic(interval: float, func: Callable[[], Awaitable[None]]) -> None:
    while True:
        await func()
        await asyncio.sleep(interval)


def _ensure_side(value: Any) -> Literal["buy", "sell"]:
    side = str(value).lower()
    if side not in {"buy", "sell"}:
        side = "buy"
    return cast(Literal["buy", "sell"], side)


def _ensure_type(value: Any) -> Literal["market", "limit"]:
    order_type = str(value).lower()
    if order_type not in {"market", "limit"}:
        order_type = "market"
    return cast(Literal["market", "limit"], order_type)


class OrderEngine:
    def __init__(
        self,
        *,
        broker: BrokerPlaceProto,
        bus: BusProto,
        config: Config,
        log: Any,
        orders_journal: NdjsonJournal,
        acks_journal: NdjsonJournal,
        add_inflight: Callable[[str], Awaitable[None]],
        last_trade_price: dict[str, float],
        live_enabled: bool,
    ) -> None:
        self._broker = broker
        self._bus = bus
        self._config = config
        self._log = log
        self._orders_journal = orders_journal
        self._acks_journal = acks_journal
        self._add_inflight = add_inflight
        self._last_trade_price = last_trade_price
        self._live_enabled = live_enabled
        self._halt_detail: dict[str, Any] = {}

    @property
    def price_cache(self) -> dict[str, float]:
        return self._last_trade_price

    async def handle_event(self, event: dict[str, Any]) -> None:
        intent = OrderIntent(
            id=str(event.get("intent_id")),
            ts_local_ns=int(event.get("ts_accepted_ns", time.time_ns())),
            strategy_id=str(event.get("strategy_id", "unknown")),
            symbol=str(event["symbol"]),
            side=_ensure_side(event.get("side")),
            type=_ensure_type(event.get("type")),
            qty=float(event["qty"]),
            limit_price=(
                float(event["limit_price"]) if event.get("limit_price") is not None else None
            ),
        )
        if not self._live_enabled or getattr(self._broker, "_read_only", False):
            req = map_intent_to_broker(intent)
            await self._publish_echo(intent, req)
            return

        self._halt_detail = {}
        if await self._is_halted():
            await self._publish_denial(intent, "halted", dict(self._halt_detail))
            self._log.warning("live_halted", intent_id=intent.id, **self._halt_detail)
            return

        req = map_intent_to_broker(intent)

        if not await self._enforce_micro_cap(intent, req):
            return

        ack = self._broker.place(req)
        await self._publish_ack(ack)
        await self._add_inflight(req.client_order_id)

    async def _publish_echo(self, intent: OrderIntent, req: BrokerOrderReq) -> None:
        payload = {
            "intent_id": intent.id,
            "client_order_id": req.client_order_id,
            "symbol": req.symbol,
            "side": req.side,
            "type": req.type,
            "qty": req.qty,
            "limit_price": req.limit_price,
            "ts_ns": time.time_ns(),
        }
        await self._bus.publish_json(ECHO_TOPIC, payload)
        self._orders_journal.write_lines([json.dumps(payload, separators=(",", ":"))])
        self._log.info("broker_echo", **payload)

    async def _publish_ack(self, ack: BrokerOrderAck) -> None:
        payload = {
            "client_order_id": ack.client_order_id,
            "exchange_order_id": ack.exchange_order_id,
            "ts_ns": ack.ts_ns,
        }
        await self._bus.publish_json(ACK_TOPIC, payload)
        self._acks_journal.write_lines([json.dumps(payload, separators=(",", ":"))])
        self._log.info("order_ack", **payload)

    async def _is_halted(self) -> bool:
        file_path = self._config.risk.kill_switch_file
        if kill_switch.file_tripped(file_path):
            self._halt_detail = {"source": "file"}
            return True
        try:
            redis_result = kill_switch.redis_tripped(
                self._config.redis.url, self._config.risk.kill_switch_key
            )
            redis_hit = (
                await redis_result if inspect.isawaitable(redis_result) else bool(redis_result)
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            self._log.warning("kill_switch_redis_check_failed", error=str(exc))
            return False
        if redis_hit:
            self._halt_detail = {"source": "redis"}
            return True
        return False

    async def _enforce_micro_cap(self, intent: OrderIntent, req: BrokerOrderReq) -> bool:
        ref_price = self._last_trade_price.get(req.symbol)
        if ref_price is None and req.limit_price is not None:
            ref_price = float(req.limit_price)
        if ref_price is None:
            return True
        notional = float(req.qty) * float(ref_price)
        if notional <= LIVE_MICRO_CAP_USD:
            return True
        caps = {
            "symbol": req.symbol,
            "qty": req.qty,
            "ref_price": ref_price,
            "notional": notional,
        }
        await self._publish_denial(intent, "live_micro_cap", caps)
        self._log.warning(
            "live_micro_cap_block",
            symbol=req.symbol,
            qty=req.qty,
            ref_price=ref_price,
            notional=round(notional, 6),
        )
        return False

    async def _publish_denial(
        self,
        intent: OrderIntent,
        reason: str,
        details: dict[str, Any],
    ) -> None:
        payload = {
            "intent_id": intent.id,
            "allowed": False,
            "reason": reason,
            "caps": details,
            "ts_ns": time.time_ns(),
        }
        await self._bus.publish_json(RISK_DECISIONS_TOPIC, payload)


async def run(config: Config) -> None:
    log_dir = Path(config.logging.journal_dir)
    setup_json_logging(str(log_dir))
    log = structlog.get_logger("broker.binanceus")

    bus = Bus(config.redis.url)
    api_key, api_secret = _binance_secrets(config)
    live_enabled = config.app.env == "live" and os.getenv("NJORD_ENABLE_LIVE") == "1"
    broker = BinanceUSBroker(api_key=api_key, api_secret=api_secret, read_only=not live_enabled)

    orders_journal = NdjsonJournal(log_dir / "broker.orders.ndjson")
    balances_journal = NdjsonJournal(log_dir / "broker.balances.ndjson")
    acks_journal = NdjsonJournal(log_dir / "broker.acks.ndjson")
    last_trade_price: dict[str, float] = {}

    inflight_lock = asyncio.Lock()
    inflight_client_ids: set[str] = set()

    async def add_inflight(client_order_id: str) -> None:
        async with inflight_lock:
            inflight_client_ids.add(client_order_id)

    async def remove_inflight(client_order_id: str) -> None:
        async with inflight_lock:
            inflight_client_ids.discard(client_order_id)

    async def snapshot_inflight() -> set[str]:
        async with inflight_lock:
            return set(inflight_client_ids)

    interval_override = os.getenv("NJORD_RECONCILE_INTERVAL_SEC")
    try:
        reconcile_interval = float(interval_override) if interval_override else 30.0
    except ValueError:
        reconcile_interval = 30.0
    watermark_path = Path("var/state/broker.binanceus.watermark.json")
    reconciler = ReconcileService(
        broker=broker,
        bus=bus,
        get_inflight=snapshot_inflight,
        fills_topic=config.redis.topics.fills,
        balance_topic=BALANCE_TOPIC,
        state_path=watermark_path,
        symbols=config.exchange.symbols,
        interval_s=reconcile_interval,
    )

    engine = OrderEngine(
        broker=broker,
        bus=bus,
        config=config,
        log=log,
        orders_journal=orders_journal,
        acks_journal=acks_journal,
        add_inflight=add_inflight,
        last_trade_price=last_trade_price,
        live_enabled=live_enabled,
    )

    async def publish_open_orders_snapshot() -> None:
        try:
            updates = broker.fetch_open_orders()
        except Exception as exc:
            log.warning("open_orders_snapshot_failed", error=str(exc))
            return
        if not updates:
            return
        for update in updates:
            await bus.publish_json(OPEN_ORDERS_TOPIC, update.__dict__)
        log.info("open_orders_snapshot", count=len(updates))

    async def handle_orders() -> None:
        async for event in bus.subscribe(config.redis.topics.orders):
            await engine.handle_event(event)

    async def publish_balances() -> None:
        snapshots = broker.fetch_balances()
        if not snapshots:
            return
        for snapshot in snapshots:
            payload = snapshot.__dict__
            await bus.publish_json(BALANCE_TOPIC, payload)
        balances_journal.write_lines(
            [json.dumps([s.__dict__ for s in snapshots], separators=(",", ":"))]
        )
        log.info("balances", count=len(snapshots))

    async def handle_cancels() -> None:
        if broker._read_only:
            async for message in bus.subscribe(CANCEL_TOPIC):
                log.info("cancel_ignored", message=message)
            return

        async for message in bus.subscribe(CANCEL_TOPIC):
            order_id = message.get("exchange_order_id") or message.get("order_id")
            if not order_id:
                continue
            success = broker.cancel(str(order_id))
            if not success:
                log.warning("cancel_failed", exchange_order_id=order_id)
                continue
            update = broker.last_cancel_update()
            if update:
                await bus.publish_json(OPEN_ORDERS_TOPIC, update.__dict__)
            log.info("order_cancel", exchange_order_id=order_id)
            client_id_raw = message.get("client_order_id")
            if client_id_raw:
                await remove_inflight(str(client_id_raw))

    async def stream_orders() -> None:
        async with broker.start_user_stream() as stream:
            async for updates in stream:
                for update in updates:
                    await bus.publish_json(OPEN_ORDERS_TOPIC, update.__dict__)
                    client_id = update.raw.get("clientOrderId")
                    if client_id and update.status in TERMINAL_STATUSES:
                        await remove_inflight(str(client_id))
                if updates:
                    log.info("open_orders", count=len(updates))

    await publish_open_orders_snapshot()

    tasks = [
        asyncio.create_task(handle_orders()),
        asyncio.create_task(_periodic(10.0, publish_balances)),
        asyncio.create_task(stream_orders()),
        asyncio.create_task(handle_cancels()),
        asyncio.create_task(reconciler.run()),
    ]

    ticker_topic_template = config.redis.topics.ticker

    async def capture_last_price(symbol: str, topic: str) -> None:
        async for message in bus.subscribe(topic):
            price = message.get("price")
            if price is None:
                price = message.get("last") or message.get("close")
            if price is None:
                continue
            last_trade_price[symbol] = float(price)

    for symbol in config.exchange.symbols:
        topic = ticker_topic_template.format(symbol=symbol)
        tasks.append(asyncio.create_task(capture_last_price(symbol, topic)))

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        orders_journal.close()
        balances_journal.close()
        acks_journal.close()
        await bus.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Njord BinanceUS broker service")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = load_config(args.config_root)
    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:  # pragma: no cover
        return 0
    return 0
