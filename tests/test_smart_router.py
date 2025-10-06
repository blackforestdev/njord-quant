"""Tests for SmartOrderRouter (Phase 8.8)."""

from __future__ import annotations

import time
import uuid

import pytest

from core.contracts import OrderIntent
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm
from execution.router import SmartOrderRouter
from tests.utils import InMemoryBus


class MockExecutor(BaseExecutor):
    """Mock executor for testing router logic."""

    def __init__(self, strategy_id: str, algo_type: str) -> None:
        super().__init__(strategy_id)
        self.algo_type = algo_type
        self.plan_calls: list[ExecutionAlgorithm] = []

    async def plan_execution(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Mock plan execution."""
        self.plan_calls.append(algo)

        # Generate mock OrderIntent
        intent = OrderIntent(
            id=f"intent_{uuid.uuid4().hex[:8]}",
            ts_local_ns=int(time.time() * 1e9),
            strategy_id=self.strategy_id,
            symbol=algo.symbol,
            side=algo.side,
            type="limit",
            qty=algo.total_quantity / 4,  # Simulate 4 slices
            limit_price=100.0,
            meta={
                "execution_id": algo.params.get("execution_id"),
                "slice_id": 0,
                "algo_type": self.algo_type,
            },
        )
        return [intent]


class FailingExecutor(BaseExecutor):
    """Mock executor that always fails (for error handling tests)."""

    def __init__(self, strategy_id: str) -> None:
        super().__init__(strategy_id)

    async def plan_execution(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Always raise exception."""
        raise RuntimeError("Executor failure simulation")


@pytest.mark.asyncio
async def test_router_initializes_with_executors() -> None:
    """Test router initialization with executor dict."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
        "VWAP": MockExecutor("test", "VWAP"),
    }

    router = SmartOrderRouter(bus, executors)

    assert router.bus is bus
    assert len(router.executors) == 2
    assert "TWAP" in router.executors
    assert "VWAP" in router.executors
    assert router.performance_tracker is None


@pytest.mark.asyncio
async def test_router_rejects_empty_executors() -> None:
    """Test router rejects empty executors dict."""
    bus = InMemoryBus()

    with pytest.raises(ValueError, match="executors dict must not be empty"):
        SmartOrderRouter(bus, {})


@pytest.mark.asyncio
async def test_router_selects_pov_for_high_urgency() -> None:
    """Test router selects POV algorithm for high urgency orders."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
        "POV": MockExecutor("test", "POV"),
    }
    router = SmartOrderRouter(bus, executors)

    intent = OrderIntent(
        id="parent_123",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=10.0,
        limit_price=50000.0,
    )

    # High urgency (30 seconds)
    execution_id = await router.route_order(intent, urgency_seconds=30)

    # Verify POV executor was called
    pov_executor = executors["POV"]
    assert isinstance(pov_executor, MockExecutor)
    assert len(pov_executor.plan_calls) == 1
    assert pov_executor.plan_calls[0].algo_type == "POV"

    # Verify execution ID format
    assert execution_id.startswith("sor_")


@pytest.mark.asyncio
async def test_router_selects_iceberg_for_large_orders() -> None:
    """Test router selects Iceberg algorithm for large orders."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
        "Iceberg": MockExecutor("test", "Iceberg"),
    }
    router = SmartOrderRouter(bus, executors)

    # Large order (qty = 15000, avg_volume_1h = 1000)
    intent = OrderIntent(
        id="parent_456",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="ETH/USDT",
        side="sell",
        type="limit",
        qty=15000.0,  # > 10x avg volume (1000)
        limit_price=3000.0,
    )

    await router.route_order(intent)

    # Verify Iceberg executor was called
    iceberg_executor = executors["Iceberg"]
    assert isinstance(iceberg_executor, MockExecutor)
    assert len(iceberg_executor.plan_calls) == 1
    assert iceberg_executor.plan_calls[0].algo_type == "Iceberg"


@pytest.mark.asyncio
async def test_router_defaults_to_twap() -> None:
    """Test router defaults to TWAP for normal conditions."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
        "VWAP": MockExecutor("test", "VWAP"),
    }
    router = SmartOrderRouter(bus, executors)

    intent = OrderIntent(
        id="parent_789",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=5.0,  # Small order
        limit_price=50000.0,
    )

    # No urgency, normal conditions
    await router.route_order(intent)

    # Verify TWAP executor was called
    twap_executor = executors["TWAP"]
    assert isinstance(twap_executor, MockExecutor)
    assert len(twap_executor.plan_calls) == 1
    assert twap_executor.plan_calls[0].algo_type == "TWAP"


@pytest.mark.asyncio
async def test_router_publishes_intents_to_bus() -> None:
    """Test router publishes OrderIntents to bus (no direct broker calls)."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
    }
    router = SmartOrderRouter(bus, executors)

    intent = OrderIntent(
        id="parent_999",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=10.0,
        limit_price=50000.0,
    )

    await router.route_order(intent)

    # Verify OrderIntent was published to strat.intent topic
    assert "strat.intent" in bus.published
    assert len(bus.published["strat.intent"]) == 1

    published_msg = bus.published["strat.intent"][0]
    assert "intent" in published_msg
    assert published_msg["intent"]["symbol"] == "BTC/USDT"
    assert published_msg["intent"]["side"] == "buy"


@pytest.mark.asyncio
async def test_router_handles_executor_failures() -> None:
    """Test router handles executor failures gracefully."""
    bus = InMemoryBus()
    executors = {
        "TWAP": FailingExecutor("test"),
    }
    router = SmartOrderRouter(bus, executors)

    intent = OrderIntent(
        id="parent_fail",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=10.0,
        limit_price=50000.0,
    )

    # Should raise RuntimeError with descriptive message
    with pytest.raises(RuntimeError, match="Executor FailingExecutor failed to plan execution"):
        await router.route_order(intent)


@pytest.mark.asyncio
async def test_router_validates_algorithm_availability() -> None:
    """Test router validates selected algorithm is available."""
    bus = InMemoryBus()
    # Only VWAP available, but router may select POV/Iceberg
    executors = {
        "VWAP": MockExecutor("test", "VWAP"),
    }
    router = SmartOrderRouter(bus, executors)

    # This should trigger POV selection (high urgency)
    # But POV is not available, so should raise error
    intent = OrderIntent(
        id="parent_missing",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=10.0,
        limit_price=50000.0,
    )

    # High urgency should select POV, but it's not available
    # Router should fall back to available algorithm (VWAP)
    await router.route_order(intent, urgency_seconds=30)

    # Verify fallback worked
    vwap_executor = executors["VWAP"]
    assert isinstance(vwap_executor, MockExecutor)
    assert len(vwap_executor.plan_calls) == 1


@pytest.mark.asyncio
async def test_router_packs_execution_metadata() -> None:
    """Test router packs execution metadata into OrderIntent.meta."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
    }
    router = SmartOrderRouter(bus, executors)

    parent_intent = OrderIntent(
        id="parent_meta",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=10.0,
        limit_price=50000.0,
    )

    execution_id = await router.route_order(parent_intent)

    # Verify published intent includes metadata
    published_msg = bus.published["strat.intent"][0]
    intent_meta = published_msg["intent"]["meta"]

    assert "execution_id" in intent_meta
    assert intent_meta["execution_id"] == execution_id
    assert "algo_type" in intent_meta
    assert intent_meta["algo_type"] == "TWAP"


@pytest.mark.asyncio
async def test_router_default_duration_scales_with_quantity() -> None:
    """Test router calculates default duration based on order size."""
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
    }
    router = SmartOrderRouter(bus, executors)

    # Small order (< 10)
    small_intent = OrderIntent(
        id="small",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=5.0,
        limit_price=50000.0,
    )

    await router.route_order(small_intent)
    twap_executor = executors["TWAP"]
    assert isinstance(twap_executor, MockExecutor)
    small_duration = twap_executor.plan_calls[0].duration_seconds
    assert small_duration == 300  # 5 minutes

    # Medium order (< 100)
    medium_intent = OrderIntent(
        id="medium",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=50.0,
        limit_price=50000.0,
    )

    await router.route_order(medium_intent)
    medium_duration = twap_executor.plan_calls[1].duration_seconds
    assert medium_duration == 600  # 10 minutes

    # Large order (>= 100)
    large_intent = OrderIntent(
        id="large",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=200.0,
        limit_price=50000.0,
    )

    await router.route_order(large_intent)
    large_duration = twap_executor.plan_calls[2].duration_seconds
    assert large_duration == 900  # 15 minutes


@pytest.mark.asyncio
async def test_router_multi_venue_support() -> None:
    """Test router supports multi-venue routing via metadata.

    Note: Multi-venue support is encoded in OrderIntent.meta.
    Future phases will add venue-specific routing logic.
    """
    bus = InMemoryBus()
    executors = {
        "TWAP": MockExecutor("test", "TWAP"),
    }
    router = SmartOrderRouter(bus, executors)

    intent = OrderIntent(
        id="parent_venue",
        ts_local_ns=int(time.time() * 1e9),
        strategy_id="test",
        symbol="BTC/USDT",
        side="buy",
        type="limit",
        qty=10.0,
        limit_price=50000.0,
        meta={"preferred_venue": "binance"},
    )

    execution_id = await router.route_order(intent)

    # Verify published intent preserves venue preference in metadata
    # (specific venue routing logic in future phases)
    assert execution_id is not None
    assert "strat.intent" in bus.published
