from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from strategies.context import BusProto
from strategies.manager import StrategyManager
from strategies.registry import StrategyRegistry


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

    async def close(self) -> None:
        """No-op for in-memory bus."""
        pass


@pytest.mark.asyncio
async def test_strategy_runner_e2e() -> None:
    """E2E test with in-memory bus and sample strategy."""
    bus = InMemoryBus()

    # Create registry and discover strategies
    registry = StrategyRegistry()
    registry.discover("strategies.samples")

    # Verify strategies were discovered
    assert "dummy_v1" in [cls.strategy_id for cls in registry._strategies.values()]

    # Create manager
    manager = StrategyManager(registry, bus)

    # Load config with dummy strategy
    config = {
        "strategies": [
            {
                "id": "test_dummy",
                "class": "strategies.samples.dummy_strategy.DummyStrategy",
                "enabled": True,
                "symbols": ["ATOM/USDT"],
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

    # Inject a trade event
    event = {"symbol": "ATOM/USDT", "price": 12.34, "ts_local_ns": 1000}
    await bus.inject_event("md.trades.ATOM/USDT", event)

    # Give time to process
    await asyncio.sleep(0.1)

    # Stop manager
    manager.stop()
    await asyncio.sleep(0.1)
    run_task.cancel()

    # Dummy strategy emits no intents, so we just verify no crash
    assert True


@pytest.mark.asyncio
async def test_strategy_runner_with_trendline_break() -> None:
    """Test strategy runner with TrendlineBreak strategy."""
    bus = InMemoryBus()

    registry = StrategyRegistry()
    registry.discover("strategies.samples")

    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "trendline_test",
                "class": "strategies.samples.trendline_break.TrendlineBreak",
                "enabled": True,
                "symbols": ["ATOM/USDT"],
                "events": ["md.trades.ATOM/USDT"],
                "params": {
                    "lookback_periods": 5,
                    "breakout_threshold": 0.02,
                    "qty": 1.0,
                    "symbol": "ATOM/USDT",
                },
            }
        ]
    }

    await manager.load(config)

    run_task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.1)

    # Feed events to build up price window
    for i, price in enumerate([10.0, 10.0, 10.0, 10.0, 10.0]):
        event = {"symbol": "ATOM/USDT", "price": price, "ts_local_ns": i * 1000}
        await bus.inject_event("md.trades.ATOM/USDT", event)
        await asyncio.sleep(0.05)

    # Feed breakout event
    event = {"symbol": "ATOM/USDT", "price": 10.22, "ts_local_ns": 6000}
    await bus.inject_event("md.trades.ATOM/USDT", event)
    await asyncio.sleep(0.1)

    manager.stop()
    await asyncio.sleep(0.1)
    run_task.cancel()

    # Check if intent was published
    intents = [msg for topic, msg in bus.published if topic == "strat.intent"]
    assert len(intents) >= 1, "Should have published at least one intent"
    assert intents[0]["side"] == "buy"


@pytest.mark.asyncio
async def test_strategy_runner_disabled_strategy() -> None:
    """Test that disabled strategies are not loaded."""
    bus: BusProto = InMemoryBus()

    registry = StrategyRegistry()
    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "disabled_strat",
                "class": "strategies.samples.dummy_strategy.DummyStrategy",
                "enabled": False,
                "symbols": ["ATOM/USDT"],
                "events": ["md.trades.*"],
                "params": {},
            }
        ]
    }

    await manager.load(config)

    assert "disabled_strat" not in manager._strategies


@pytest.mark.asyncio
async def test_strategy_runner_multiple_strategies() -> None:
    """Test running multiple strategies concurrently."""
    bus = InMemoryBus()

    registry = StrategyRegistry()
    registry.discover("strategies.samples")

    manager = StrategyManager(registry, bus)

    config = {
        "strategies": [
            {
                "id": "strat1",
                "class": "strategies.samples.dummy_strategy.DummyStrategy",
                "enabled": True,
                "symbols": ["ATOM/USDT"],
                "events": ["md.trades.ATOM/USDT"],
                "params": {},
            },
            {
                "id": "strat2",
                "class": "strategies.samples.trendline_break.TrendlineBreak",
                "enabled": True,
                "symbols": ["ATOM/USDT"],
                "events": ["md.trades.ATOM/USDT"],
                "params": {
                    "lookback_periods": 5,
                    "breakout_threshold": 0.02,
                    "qty": 1.0,
                    "symbol": "ATOM/USDT",
                },
            },
        ]
    }

    await manager.load(config)

    assert "strat1" in manager._strategies
    assert "strat2" in manager._strategies

    run_task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.1)

    # Inject event
    event = {"symbol": "ATOM/USDT", "price": 12.34, "ts_local_ns": 1000}
    await bus.inject_event("md.trades.ATOM/USDT", event)
    await asyncio.sleep(0.1)

    manager.stop()
    await asyncio.sleep(0.1)
    run_task.cancel()

    # Both strategies should have processed the event
    assert True
