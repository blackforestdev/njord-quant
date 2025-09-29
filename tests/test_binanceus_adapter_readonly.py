from __future__ import annotations

import pytest

from apps.broker_binanceus.adapter import BinanceUSBroker
from core.broker import BrokerOrderReq


def test_read_only_mode_blocks_place(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    if importlib.util.find_spec("ccxt") is None:
        pytest.skip("ccxt not installed")

    broker = BinanceUSBroker(api_key=None, api_secret=None, read_only=True)

    req = BrokerOrderReq(
        symbol="ATOM/USDT",
        side="buy",
        type="limit",
        qty=1.0,
        limit_price=10.0,
        client_order_id="NJ-test",
    )

    with pytest.raises(RuntimeError):
        broker.place(req)

    class DummyExchange:
        def fetch_balance(self) -> dict[str, dict[str, float]]:
            return {"total": {"USDT": 100.0}, "free": {"USDT": 90.0}, "used": {"USDT": 10.0}}

        def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(broker, "_exchange", DummyExchange())

    assert broker.fetch_balances()[0].asset == "USDT"
    assert broker.fetch_open_orders() == []
