from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import Any

import pytest

from core.contracts import OrderIntent
from strategies.base import StrategyBase
from strategies.context import BusProto
from strategies.manager import StrategyManager
from strategies.registry import StrategyRegistry


class TestStrategy(StrategyBase):
    """Test strategy that echoes trade events as buy intents."""

    strategy_id = "test_strategy"

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        if "symbol" in event and "price" in event:
            return [
                OrderIntent(
                    id=f"intent-{event['price']}",
                    ts_local_ns=event.get("ts_local_ns", 0),
                    strategy_id=self.strategy_id,
                    symbol=event["symbol"],
                    side="buy",
                    type="market",
                    qty=1.0,
                    limit_price=None,
                )
            ]
        return []


class InMemoryBus:
    """In-memory bus for testing."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.channels: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, payload))

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        if topic not in self.channels:
            self.channels[topic] = asyncio.Queue()

        async def stream() -> AsyncIterator[dict[str, Any]]:
            queue = self.channels[topic]
            while True:
                msg = await queue.get()
                yield msg

        return stream()

    async def inject_event(self, topic: str, payload: dict[str, Any]) -> None:
        """Inject an event into a topic for testing."""
        if topic not in self.channels:
            self.channels[topic] = asyncio.Queue()
        await self.channels[topic].put(payload)


@pytest.mark.asyncio
async def test_load_strategies() -> None:
    registry = StrategyRegistry()
    registry.register(TestStrategy)

    bus: BusProto = InMemoryBus()
    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "test_strat_1",
                "class": "tests.test_strategy_manager.TestStrategy",
                "enabled": True,
                "events": ["md.trades.*"],
                "params": {"foo": "bar"},
            }
        ]
    }

    await manager.load(config)

    assert "test_strat_1" in manager._strategies


@pytest.mark.asyncio
async def test_load_disabled_strategy() -> None:
    registry = StrategyRegistry()
    bus: BusProto = InMemoryBus()
    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "disabled_strat",
                "class": "tests.test_strategy_manager.TestStrategy",
                "enabled": False,
                "events": ["md.trades.*"],
            }
        ]
    }

    await manager.load(config)

    assert "disabled_strat" not in manager._strategies


@pytest.mark.asyncio
async def test_dispatch_event_to_strategy() -> None:
    registry = StrategyRegistry()
    registry.register(TestStrategy)

    bus = InMemoryBus()
    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "test_strat_1",
                "class": "tests.test_strategy_manager.TestStrategy",
                "enabled": True,
                "events": ["md.trades.ATOM/USDT"],
                "params": {},
            }
        ]
    }

    await manager.load(config)

    # Start manager in background
    run_task = asyncio.create_task(manager.run())

    # Give subscriptions time to set up
    await asyncio.sleep(0.1)

    # Inject event
    event = {"symbol": "ATOM/USDT", "price": 12.34, "ts_local_ns": 1000}
    await bus.inject_event("md.trades.ATOM/USDT", event)

    # Give time to process
    await asyncio.sleep(0.1)

    # Check intent was published
    manager.stop()
    await asyncio.sleep(0.1)
    run_task.cancel()

    assert len(bus.published) == 1
    topic, payload = bus.published[0]
    assert topic == "strat.intent"
    assert payload["symbol"] == "ATOM/USDT"
    assert payload["side"] == "buy"


@pytest.mark.asyncio
async def test_strategy_error_continues() -> None:
    """Test graceful degradation when strategy raises exception."""

    class BrokenStrategy(StrategyBase):
        strategy_id = "broken"

        def on_event(self, event: Any) -> Iterable[OrderIntent]:
            raise RuntimeError("Strategy crashed!")

    registry = StrategyRegistry()
    registry.register(BrokenStrategy)

    bus = InMemoryBus()
    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "broken_strat",
                "class": "tests.test_strategy_manager.BrokenStrategy",
                "enabled": True,
                "events": ["md.trades.*"],
                "params": {},
            }
        ]
    }

    await manager.load(config)

    run_task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.1)

    # Inject event
    await bus.inject_event("md.trades.*", {"symbol": "ATOM/USDT"})
    await asyncio.sleep(0.1)

    # Manager should still be running
    assert not run_task.done()

    manager.stop()
    await asyncio.sleep(0.1)
    run_task.cancel()


@pytest.mark.asyncio
async def test_reload_strategies() -> None:
    registry = StrategyRegistry()
    registry.register(TestStrategy)

    bus: BusProto = InMemoryBus()
    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "test_strat_1",
                "class": "tests.test_strategy_manager.TestStrategy",
                "enabled": True,
                "events": ["md.trades.*"],
                "params": {},
            }
        ]
    }

    await manager.load(config)
    assert "test_strat_1" in manager._strategies

    # Reload
    await manager.reload()
    assert "test_strat_1" in manager._strategies
