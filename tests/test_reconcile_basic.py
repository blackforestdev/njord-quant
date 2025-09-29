from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import structlog

from apps.broker_binanceus.adapter import BinanceUSBroker
from apps.broker_binanceus.backoff import RestRetry
from apps.broker_binanceus.reconcile import ReconcileService
from tests.utils import InMemoryBus


class FakeExchange:
    def __init__(self) -> None:
        self.open_orders: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.balance: dict[str, Any] = {
            "total": {"USDT": 100.0},
            "free": {"USDT": 80.0},
            "used": {"USDT": 20.0},
        }

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return [dict(order) for order in self.open_orders]

    def fetch_my_trades(self, since: int | None = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for trade in self.trades:
            timestamp = int(trade.get("timestamp", 0))
            if since is not None and timestamp < since:
                continue
            result.append(dict(trade))
        return result

    def fetch_order(
        self, symbol: Any = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        client_id = None
        if params:
            client_id = params.get("clientOrderId")
        for order in self.open_orders:
            if client_id and order.get("clientOrderId") == client_id:
                return dict(order)
        raise RuntimeError("order not found")

    def fetch_balance(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(self.balance)))


def make_broker() -> BinanceUSBroker:
    broker = BinanceUSBroker.__new__(BinanceUSBroker)
    broker._exchange = FakeExchange()
    broker._pro_exchange = None
    broker._read_only = True
    broker._listen_key = None
    broker._last_cancel_update = None
    broker._rest_retry = RestRetry(
        sleep_fn=lambda _seconds: None, logger=structlog.get_logger("test")
    )
    broker._log = structlog.get_logger("test")
    return broker


@pytest.mark.asyncio
async def test_reconcile_emits_fill_and_updates_watermark(tmp_path: Path) -> None:
    broker = make_broker()
    exchange = cast(FakeExchange, broker._exchange)
    client_order_id = "NJ-TEST-1"
    exchange.open_orders.append(
        {
            "id": "42",
            "clientOrderId": client_order_id,
            "status": "NEW",
            "filled": 0.0,
            "average": None,
            "timestamp": 1,
        }
    )
    trade_ts = 1_720_000_000_000
    exchange.trades.append(
        {
            "id": "trade-1",
            "order": "42",
            "clientOrderId": client_order_id,
            "symbol": "ATOM/USDT",
            "side": "buy",
            "amount": 1.25,
            "price": 12.5,
            "timestamp": trade_ts,
            "fee": {"cost": 0.01},
        }
    )

    bus = InMemoryBus()

    async def get_inflight() -> set[str]:
        return {client_order_id}

    state_path = tmp_path / "var" / "state" / "broker.binanceus.watermark.json"
    service = ReconcileService(
        broker=broker,
        bus=bus,
        get_inflight=get_inflight,
        fills_topic="fills.new",
        balance_topic="broker.balances",
        state_path=state_path,
        symbols=["ATOM/USDT"],
        interval_s=0.01,
    )

    await service.reconcile_once()
    assert bus.published["fills.new"], "expected fill event"
    fill_payload = bus.published["fills.new"][0]
    assert fill_payload["order_id"] == "42"
    assert fill_payload["qty"] == pytest.approx(1.25)
    assert fill_payload["meta"]["exchange_trade_id"] == "trade-1"

    assert bus.published["broker.balances"], "expected balance snapshot"

    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["timestamp_ms"] == trade_ts
    assert state["trade_id"] == "trade-1"

    await service.reconcile_once()
    assert len(bus.published["fills.new"]) == 1, "fill should not duplicate"
