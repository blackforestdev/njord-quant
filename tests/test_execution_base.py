"""Tests for execution layer foundations (Phase 8.0)."""

import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

from core.bus import Bus, BusProto
from core.contracts import FillEvent, OrderIntent
from execution.adapters import SyncExecutionWrapper
from execution.base import BaseExecutor


# Mock ExecutionAlgorithm for testing (Phase 8.1 will define real one)
class MockExecutionAlgorithm:
    def __init__(self, symbol: str, quantity: float) -> None:
        self.symbol = symbol
        self.quantity = quantity


# Concrete executor for testing
class MockExecutor(BaseExecutor):
    """Mock executor that emits OrderIntents with execution metadata."""

    async def plan_execution(self, algo: Any) -> list[OrderIntent]:
        """Generate OrderIntents with execution metadata in meta field."""
        execution_id = f"exec_{int(time.time() * 1e9)}"
        slice_id = "slice_0"

        # CRITICAL: Pack execution metadata into OrderIntent.meta
        intent = OrderIntent(
            id=f"intent_{execution_id}_{slice_id}",
            ts_local_ns=int(time.time() * 1e9),
            strategy_id=self.strategy_id,
            symbol=algo.symbol,
            side="buy",
            type="limit",
            qty=algo.quantity,
            limit_price=100.0,
            meta={
                "execution_id": execution_id,
                "slice_id": slice_id,
                "algo_type": "TEST",
            },
        )

        return [intent]


# Mock Bus for testing
class MockBus:
    """Mock bus for testing without Redis."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.messages: dict[str, list[dict[str, Any]]] = {}

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, payload))

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        async def stream() -> AsyncIterator[dict[str, Any]]:
            # Return pre-loaded messages for this topic
            for msg in self.messages.get(topic, []):
                yield msg

        return stream()

    def add_message(self, topic: str, message: dict[str, Any]) -> None:
        """Add a message to be returned by subscribe()."""
        if topic not in self.messages:
            self.messages[topic] = []
        self.messages[topic].append(message)


def test_bus_proto_compatibility() -> None:
    """Verify BusProto matches Bus interface."""
    # This test verifies that Bus implements BusProto
    # If Bus doesn't match BusProto, mypy will fail
    bus: BusProto = Bus(url="redis://localhost:6379/0")
    assert bus is not None


@pytest.mark.asyncio
async def test_base_executor_emits_order_intents() -> None:
    """Verify BaseExecutor emits OrderIntents (not broker calls)."""
    executor = MockExecutor(strategy_id="strat_test")
    algo = MockExecutionAlgorithm(symbol="BTC/USDT", quantity=0.1)

    intents = await executor.plan_execution(algo)

    assert len(intents) == 1
    assert isinstance(intents[0], OrderIntent)
    assert intents[0].symbol == "BTC/USDT"
    assert intents[0].qty == 0.1
    assert intents[0].strategy_id == "strat_test"


@pytest.mark.asyncio
async def test_order_intent_meta_packing() -> None:
    """Verify OrderIntent.meta contains execution_id and slice_id."""
    executor = MockExecutor(strategy_id="strat_test")
    algo = MockExecutionAlgorithm(symbol="BTC/USDT", quantity=0.1)

    intents = await executor.plan_execution(algo)

    # Verify meta contains execution metadata
    meta = intents[0].meta
    assert "execution_id" in meta
    assert "slice_id" in meta
    assert "algo_type" in meta
    assert meta["execution_id"].startswith("exec_")
    assert meta["slice_id"] == "slice_0"
    assert meta["algo_type"] == "TEST"


@pytest.mark.asyncio
async def test_round_trip_order_intent_to_fill_recovery() -> None:
    """Verify round-trip: OrderIntent.meta → Fill → recovery.

    Simulates the flow:
    1. Executor generates OrderIntent with execution_id in meta
    2. Broker executes order and generates Fill with same meta
    3. Executor can recover execution_id from Fill to track progress
    """
    executor = MockExecutor(strategy_id="strat_test")
    algo = MockExecutionAlgorithm(symbol="BTC/USDT", quantity=0.1)

    # Step 1: Generate OrderIntent
    intents = await executor.plan_execution(algo)
    intent = intents[0]
    execution_id = intent.meta["execution_id"]

    # Step 2: Simulate broker generating Fill with same meta
    fill = FillEvent(
        order_id=intent.id,
        symbol=intent.symbol,
        side=intent.side,
        qty=intent.qty,
        price=100.0,
        ts_fill_ns=int(time.time() * 1e9),
        fee=0.1,
        meta=intent.meta,  # Broker copies meta from OrderIntent
    )

    # Step 3: Verify we can recover execution_id from Fill
    assert fill.meta["execution_id"] == execution_id
    assert fill.meta["slice_id"] == "slice_0"


@pytest.mark.asyncio
async def test_track_fills_filters_by_execution_id() -> None:
    """Verify track_fills() filters fills by execution_id."""
    executor = MockExecutor(strategy_id="strat_test")
    mock_bus = MockBus()

    # Add fills for different executions
    mock_bus.add_message(
        "fills.new",
        {
            "order_id": "order_1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "qty": 0.1,
            "price": 100.0,
            "ts_fill_ns": int(time.time() * 1e9),
            "fee": 0.1,
            "meta": {"execution_id": "exec_123", "slice_id": "slice_0"},
        },
    )
    mock_bus.add_message(
        "fills.new",
        {
            "order_id": "order_2",
            "symbol": "ETH/USDT",
            "side": "sell",
            "qty": 1.0,
            "price": 2000.0,
            "ts_fill_ns": int(time.time() * 1e9),
            "fee": 2.0,
            "meta": {"execution_id": "exec_456", "slice_id": "slice_1"},
        },
    )

    # Track fills for exec_123 only
    fills = []
    async for fill in executor.track_fills(mock_bus, "exec_123"):
        fills.append(fill)

    # Should only get fills for exec_123
    assert len(fills) == 1
    assert fills[0].order_id == "order_1"
    assert fills[0].symbol == "BTC/USDT"
    assert fills[0].meta["execution_id"] == "exec_123"


def test_sync_wrapper_in_pure_sync_context() -> None:
    """Verify SyncExecutionWrapper works in pure sync context."""
    executor = MockExecutor(strategy_id="strat_test")
    wrapper = SyncExecutionWrapper(executor)
    algo = MockExecutionAlgorithm(symbol="BTC/USDT", quantity=0.1)

    # This should work (no event loop running)
    intents = wrapper.plan_execution_sync(algo)

    assert len(intents) == 1
    assert intents[0].symbol == "BTC/USDT"


@pytest.mark.asyncio
async def test_sync_wrapper_raises_in_event_loop() -> None:
    """Verify SyncExecutionWrapper raises if called from event loop."""
    executor = MockExecutor(strategy_id="strat_test")
    wrapper = SyncExecutionWrapper(executor)
    algo = MockExecutionAlgorithm(symbol="BTC/USDT", quantity=0.1)

    # This should raise because we're in an async context
    with pytest.raises(RuntimeError, match="cannot be called from within an existing event loop"):
        wrapper.plan_execution_sync(algo)


def test_base_executor_is_abstract() -> None:
    """Verify BaseExecutor cannot be instantiated directly."""
    with pytest.raises(TypeError, match="abstract"):
        BaseExecutor(strategy_id="test")  # type: ignore[abstract]
