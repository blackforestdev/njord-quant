from __future__ import annotations

from typing import Any

from apps.broker_binanceus.adapter import BinanceUSBroker
from core.broker import BrokerOrderUpdate


class CancelExchange:
    def __init__(self) -> None:
        self.canceled: list[str] = []

    def cancel_order(self, order_id: str) -> None:
        self.canceled.append(order_id)

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return []


class _TestBroker(BinanceUSBroker):
    def __init__(self, exchange: CancelExchange) -> None:
        self._exchange = exchange
        self._pro_exchange = None
        self._read_only = False
        self._listen_key = None
        self._last_cancel_update = None


def make_live_broker(fake_exchange: CancelExchange) -> BinanceUSBroker:
    return _TestBroker(fake_exchange)


def test_cancel_emits_update() -> None:
    fake = CancelExchange()
    broker = make_live_broker(fake)

    assert broker.cancel("EX-1") is True
    assert fake.canceled == ["EX-1"]

    update = broker.last_cancel_update()
    assert isinstance(update, BrokerOrderUpdate)
    assert update.exchange_order_id == "EX-1"
    assert update.status == "CANCELED"
    assert update.raw["event"] == "cancel"
