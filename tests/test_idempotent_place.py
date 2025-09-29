from __future__ import annotations

import time
from typing import Any, cast

import pytest

from apps.broker_binanceus.adapter import BinanceUSBroker, DuplicateClientOrderIdError
from core.broker import BrokerOrderReq


class DuplicateExchange:
    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_by_exchange: dict[str, dict[str, Any]] = {}
        self.counter = 0

    def create_order(
        self,
        *,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: float | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if "clientOrderId" not in params:
            raise ValueError("clientOrderId required")
        client_id: str = cast(str, params["clientOrderId"])
        if client_id in self.orders:
            raise Exception("Duplicate clientOrderId")
        self.counter += 1
        order = {
            "id": f"EX-{self.counter}",
            "clientOrderId": client_id,
            "timestamp": int(time.time() * 1000),
        }
        self.orders[client_id] = order
        exchange_id = str(order["id"])
        self.order_by_exchange[exchange_id] = order
        return order

    def fetch_order(self, order_id: str | None, params: dict[str, Any]) -> dict[str, Any]:
        client_obj = params.get("clientOrderId")
        if client_obj is None:
            raise KeyError("clientOrderId")
        client_id: str = cast(str, client_obj)
        if client_id in self.orders:
            return self.orders[client_id]
        raise KeyError(client_id)

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return list(self.order_by_exchange.values())

    def cancel_order(self, order_id: str) -> None:
        self.order_by_exchange.pop(order_id, None)


class _TestBroker(BinanceUSBroker):
    def __init__(self, exchange: DuplicateExchange) -> None:
        self._exchange = exchange
        self._pro_exchange = None
        self._read_only = False
        self._listen_key = None
        self._last_cancel_update = None


def make_live_broker(fake_exchange: DuplicateExchange) -> BinanceUSBroker:
    return _TestBroker(fake_exchange)


def test_idempotent_place_returns_existing_ack() -> None:
    fake = DuplicateExchange()
    broker = make_live_broker(fake)

    req = BrokerOrderReq(
        symbol="ATOM/USDT",
        side="buy",
        type="limit",
        qty=1.0,
        limit_price=10.0,
        client_order_id="cid-1",
    )

    first = broker.place(req)
    duplicate = broker.place(req)

    assert duplicate.exchange_order_id == first.exchange_order_id
    assert duplicate.client_order_id == first.client_order_id

    class ErrorExchange(DuplicateExchange):
        def create_order(
            self,
            *,
            symbol: str,
            type: str,
            side: str,
            amount: float,
            price: float | None,
            params: dict[str, Any],
        ) -> dict[str, Any]:
            raise Exception("Duplicate client order id")

        def fetch_order(self, order_id: str | None, params: dict[str, Any]) -> dict[str, Any]:
            raise Exception("Order not found")

    broker._exchange = ErrorExchange()
    with pytest.raises(DuplicateClientOrderIdError):
        broker.place(req)
