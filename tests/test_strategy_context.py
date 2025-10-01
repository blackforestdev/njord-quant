from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from core.contracts import PositionSnapshot
from strategies.context import BusProto, StrategyContext


class EmptyAsyncIterator(AsyncIterator[dict[str, Any]]):
    async def __anext__(self) -> dict[str, Any]:
        raise StopAsyncIteration


class DummyBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, payload))

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        return EmptyAsyncIterator()


def make_snapshot(symbol: str) -> PositionSnapshot:
    return PositionSnapshot(symbol=symbol, qty=0.0, avg_price=0.0, realized_pnl=0.0, ts_ns=0)


def test_strategy_context_holds_state() -> None:
    bus: BusProto = DummyBus()
    positions = {"ATOM/USDT": make_snapshot("ATOM/USDT")}
    prices = {"ATOM/USDT": 12.34}
    config = {"window": 5}

    ctx = StrategyContext(
        strategy_id="test",
        bus=bus,
        positions=positions,
        prices=prices,
        config=config,
    )

    assert ctx.strategy_id == "test"
    assert ctx.bus is bus
    assert ctx.positions["ATOM/USDT"].symbol == "ATOM/USDT"
    assert ctx.prices["ATOM/USDT"] == 12.34
    assert ctx.config["window"] == 5


def test_strategy_context_is_immutable() -> None:
    bus: BusProto = DummyBus()
    ctx = StrategyContext(
        strategy_id="immutable",
        bus=bus,
        positions={},
        prices={},
        config={},
    )

    with pytest.raises(FrozenInstanceError):
        ctx.strategy_id = "other"  # type: ignore[misc]
