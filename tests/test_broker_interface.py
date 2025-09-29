from __future__ import annotations

from typing import Any

from core.broker import (
    BalanceSnapshot,
    BrokerOrderAck,
    BrokerOrderReq,
    BrokerOrderUpdate,
    IBroker,
    map_intent_to_broker,
)
from core.contracts import OrderIntent


def make_intent(**kwargs: Any) -> OrderIntent:
    base: dict[str, Any] = {
        "id": "abc1234567890",
        "ts_local_ns": 1,
        "strategy_id": "s1",
        "symbol": "ATOM/USDT",
        "side": "buy",
        "type": "limit",
        "qty": 1.0,
        "limit_price": 10.0,
    }
    base.update(kwargs)
    return OrderIntent(**base)


def test_map_intent_to_broker_basic() -> None:
    intent = make_intent()
    req = map_intent_to_broker(intent)

    assert isinstance(req, BrokerOrderReq)
    assert req.client_order_id.startswith("NJ-")
    assert req.symbol == "ATOM/USDT"
    assert req.limit_price == 10.0


def test_broker_models_allow_round_trip() -> None:
    req = BrokerOrderReq(
        symbol="BTC/USDT",
        side="buy",
        type="market",
        qty=0.5,
        limit_price=None,
        client_order_id="NJ-1",
    )
    ack = BrokerOrderAck(client_order_id="NJ-1", exchange_order_id="E1", ts_ns=123)
    update = BrokerOrderUpdate(
        exchange_order_id="E1",
        status="FILLED",
        filled_qty=0.5,
        avg_price=10.0,
        ts_ns=456,
    )
    balance = BalanceSnapshot(asset="USDT", free=1000.0, locked=0.0, ts_ns=789)

    assert req.qty == 0.5
    assert ack.exchange_order_id == "E1"
    assert update.status == "FILLED"
    assert balance.asset == "USDT"


def test_ibroker_interface_can_be_implemented() -> None:
    class DummyBroker(IBroker):
        def place(self, req: BrokerOrderReq) -> BrokerOrderAck:
            return BrokerOrderAck(
                client_order_id=req.client_order_id,
                exchange_order_id="EX-1",
                ts_ns=0,
            )

        def cancel(self, exchange_order_id: str) -> bool:
            return exchange_order_id == "EX-1"

        def fetch_open_orders(self, symbol: str | None = None) -> list[BrokerOrderUpdate]:
            return []

        def fetch_balances(self) -> list[BalanceSnapshot]:
            return []

    broker = DummyBroker()
    intent = make_intent()
    req = map_intent_to_broker(intent)
    ack = broker.place(req)

    assert ack.client_order_id == req.client_order_id
    assert broker.cancel(ack.exchange_order_id) is True
    assert broker.fetch_open_orders() == []
    assert broker.fetch_balances() == []
