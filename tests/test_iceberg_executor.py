"""Tests for Iceberg executor (Phase 8.4)."""

import asyncio
import time
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from core.contracts import FillEvent, OrderIntent
from execution.contracts import ExecutionAlgorithm
from execution.iceberg import IcebergExecutor


def test_iceberg_executor_valid() -> None:
    """Verify IcebergExecutor creation with valid parameters."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1, replenish_threshold=0.5)

    assert executor.strategy_id == "test_strat"
    assert executor.visible_ratio == 0.1
    assert executor.replenish_threshold == 0.5


def test_iceberg_executor_validation_visible_ratio() -> None:
    """Verify IcebergExecutor rejects invalid visible_ratio."""
    # Zero
    with pytest.raises(ValueError, match="visible_ratio must be in"):
        IcebergExecutor(strategy_id="test_strat", visible_ratio=0.0)

    # Negative
    with pytest.raises(ValueError, match="visible_ratio must be in"):
        IcebergExecutor(strategy_id="test_strat", visible_ratio=-0.1)

    # > 1
    with pytest.raises(ValueError, match="visible_ratio must be in"):
        IcebergExecutor(strategy_id="test_strat", visible_ratio=1.5)


def test_iceberg_executor_validation_replenish_threshold() -> None:
    """Verify IcebergExecutor rejects invalid replenish_threshold."""
    # Zero
    with pytest.raises(ValueError, match="replenish_threshold must be in"):
        IcebergExecutor(strategy_id="test_strat", replenish_threshold=0.0)

    # Negative
    with pytest.raises(ValueError, match="replenish_threshold must be in"):
        IcebergExecutor(strategy_id="test_strat", replenish_threshold=-0.5)

    # > 1
    with pytest.raises(ValueError, match="replenish_threshold must be in"):
        IcebergExecutor(strategy_id="test_strat", replenish_threshold=1.5)


@pytest.mark.asyncio
async def test_iceberg_plan_execution_basic() -> None:
    """Verify Iceberg plan_execution returns single initial intent."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1)

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)

    # Should return 1 intent (initial visible portion)
    assert len(intents) == 1
    assert isinstance(intents[0], OrderIntent)


@pytest.mark.asyncio
async def test_iceberg_plan_execution_visible_quantity() -> None:
    """Verify Iceberg shows only visible_ratio of total quantity."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.2)

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=5.0,
        duration_seconds=3600,
        params={"limit_price": 3000.0},
    )

    intents = await executor.plan_execution(algo)

    # Initial intent should show 20% of 5.0 = 1.0
    assert intents[0].qty == pytest.approx(1.0)

    # Metadata should contain total quantity (hidden)
    assert intents[0].meta["total_quantity"] == 5.0
    assert intents[0].meta["visible_ratio"] == 0.2


@pytest.mark.asyncio
async def test_iceberg_plan_execution_limit_order() -> None:
    """Verify Iceberg creates limit orders with specified price."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1)

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2.0,
        duration_seconds=3600,
        params={"limit_price": 48000.0},
    )

    intents = await executor.plan_execution(algo)

    assert intents[0].type == "limit"
    assert intents[0].limit_price == 48000.0


@pytest.mark.asyncio
async def test_iceberg_plan_execution_missing_limit_price() -> None:
    """Verify Iceberg raises error when limit_price missing."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1)

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2.0,
        duration_seconds=3600,
        params={},  # Missing limit_price
    )

    with pytest.raises(ValueError, match=r"Either limit_price or price_levels must be provided"):
        await executor.plan_execution(algo)


@pytest.mark.asyncio
async def test_iceberg_plan_execution_invalid_limit_price() -> None:
    """Verify Iceberg validates limit_price."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1)

    # Zero price
    algo_zero = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2.0,
        duration_seconds=3600,
        params={"limit_price": 0.0},
    )

    with pytest.raises(ValueError, match="limit_price must be > 0"):
        await executor.plan_execution(algo_zero)

    # Invalid type
    algo_str = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2.0,
        duration_seconds=3600,
        params={"limit_price": "50000"},
    )

    with pytest.raises(TypeError, match="limit_price must be a number"):
        await executor.plan_execution(algo_str)


@pytest.mark.asyncio
async def test_iceberg_plan_execution_meta_packing() -> None:
    """Verify Iceberg packs execution metadata into OrderIntent.meta."""
    executor = IcebergExecutor(
        strategy_id="test_strat", visible_ratio=0.15, replenish_threshold=0.6
    )

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)

    intent = intents[0]
    assert "execution_id" in intent.meta
    assert intent.meta["execution_id"].startswith("iceberg_")
    assert intent.meta["slice_id"] == f"{intent.meta['execution_id']}_slice_0"
    assert intent.meta["algo_type"] == "Iceberg"
    assert intent.meta["slice_idx"] == 0
    assert intent.meta["total_quantity"] == 10.0
    assert intent.meta["visible_ratio"] == 0.15
    assert intent.meta["replenish_threshold"] == 0.6


@pytest.mark.asyncio
async def test_iceberg_plan_execution_intent_attributes() -> None:
    """Verify Iceberg creates OrderIntents with correct attributes."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1)

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=8.0,
        duration_seconds=3600,
        params={"limit_price": 3100.0},
    )

    intents = await executor.plan_execution(algo)

    intent = intents[0]
    assert intent.strategy_id == "test_strat"
    assert intent.symbol == "ETH/USDT"
    assert intent.side == "sell"
    assert intent.qty == pytest.approx(0.8)  # 10% of 8.0


@pytest.mark.asyncio
async def test_iceberg_monitor_and_replenish_single_cycle() -> None:
    """Verify Iceberg replenishes when threshold reached."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.2, replenish_threshold=0.5)

    # Mock bus
    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    # Initial plan
    intents = await executor.plan_execution(algo)
    execution_id = intents[0].meta["execution_id"]

    # Simulate fills reaching replenish threshold
    # Initial visible qty = 10.0 * 0.2 = 2.0
    # Replenish at 50% = 1.0 filled
    fills = [
        FillEvent(
            order_id=intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=0.5,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=25.0,
            meta=intents[0].meta.copy(),
        ),
        FillEvent(
            order_id=intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=0.5,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=25.0,
            meta=intents[0].meta.copy(),
        ),
    ]

    # Mock async generator for fills
    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    # Patch track_fills
    with patch.object(executor, "track_fills", return_value=mock_fills()):
        # Monitor and collect replenishment intents
        replenish_intents: list[OrderIntent] = []
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents.append(intent)

        # Should generate 1 replenishment intent
        assert len(replenish_intents) == 1

        # Replenishment intent should have same visible quantity
        assert replenish_intents[0].qty == pytest.approx(2.0)
        assert replenish_intents[0].meta["execution_id"] == execution_id
        assert replenish_intents[0].meta["slice_idx"] == 1


@pytest.mark.asyncio
async def test_iceberg_monitor_and_replenish_multiple_cycles() -> None:
    """Verify Iceberg handles multiple replenishment cycles."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1, replenish_threshold=1.0)

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=5.0,
        duration_seconds=3600,
        params={"limit_price": 3000.0},
    )

    # Initial plan
    intents = await executor.plan_execution(algo)
    execution_id = intents[0].meta["execution_id"]

    # Simulate multiple fill cycles with complete metadata
    # Visible qty = 5.0 * 0.1 = 0.5 per slice
    # Replenish at 100% = 0.5 filled each time
    # We'll drive exactly 3 cycles (0.5 + 0.5 + 0.5 = 1.5 filled, 3.5 remaining)
    fills = [
        # Cycle 0: Fill initial slice completely (triggers replenish to slice_1)
        FillEvent(
            order_id=intents[0].id,
            symbol="ETH/USDT",
            side="sell",
            qty=0.5,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=1.5,
            meta=intents[0].meta.copy(),  # Complete metadata from intent
        ),
        # Cycle 1: Fill slice_1 completely (triggers replenish to slice_2)
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="ETH/USDT",
            side="sell",
            qty=0.5,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=1.5,
            meta={
                "execution_id": execution_id,
                "slice_id": f"{execution_id}_slice_1",
                "algo_type": "Iceberg",
                "slice_idx": 1,
                "total_quantity": 5.0,
                "visible_ratio": 0.1,
                "replenish_threshold": 1.0,
            },
        ),
        # Cycle 2: Fill slice_2 completely (triggers replenish to slice_3)
        FillEvent(
            order_id=f"{execution_id}_slice_2",
            symbol="ETH/USDT",
            side="sell",
            qty=0.5,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=1.5,
            meta={
                "execution_id": execution_id,
                "slice_id": f"{execution_id}_slice_2",
                "algo_type": "Iceberg",
                "slice_idx": 2,
                "total_quantity": 5.0,
                "visible_ratio": 0.1,
                "replenish_threshold": 1.0,
            },
        ),
    ]

    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    with patch.object(executor, "track_fills", return_value=mock_fills()):
        replenish_intents: list[OrderIntent] = []
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            # Verify metadata BEFORE yielding to ensure propagation
            assert intent.meta["execution_id"] == execution_id
            assert intent.meta["algo_type"] == "Iceberg"
            assert intent.meta["total_quantity"] == 5.0
            assert "slice_id" in intent.meta
            assert "slice_idx" in intent.meta
            replenish_intents.append(intent)

        # Should generate exactly 3 replenishment intents (one per fill cycle)
        assert len(replenish_intents) == 3

        # Verify each replenishment intent has correct slice_idx
        assert replenish_intents[0].meta["slice_idx"] == 1
        assert replenish_intents[1].meta["slice_idx"] == 2
        assert replenish_intents[2].meta["slice_idx"] == 3


@pytest.mark.asyncio
async def test_iceberg_monitor_and_replenish_final_slice() -> None:
    """Verify Iceberg handles final slice smaller than visible_ratio."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.3, replenish_threshold=1.0)

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)
    execution_id = intents[0].meta["execution_id"]

    # Fill first slice (0.3)
    # Remaining = 0.7, next visible should be min(0.7, 0.3) = 0.3
    fills = [
        FillEvent(
            order_id=intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=0.3,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=15.0,
            meta=intents[0].meta.copy(),
        ),
        # Fill second slice (0.3)
        # Remaining = 0.4, next visible should be min(0.4, 0.3) = 0.3
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="BTC/USDT",
            side="buy",
            qty=0.3,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=15.0,
            meta={"execution_id": execution_id, "slice_idx": 1},
        ),
        # Fill third slice (0.3)
        # Remaining = 0.1, final slice should be 0.1 (smaller than visible_ratio)
        FillEvent(
            order_id=f"{execution_id}_slice_2",
            symbol="BTC/USDT",
            side="buy",
            qty=0.3,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=15.0,
            meta={"execution_id": execution_id, "slice_idx": 2},
        ),
    ]

    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    with patch.object(executor, "track_fills", return_value=mock_fills()):
        replenish_intents: list[OrderIntent] = []
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents.append(intent)

        # Should have final slice with qty = 0.1 (remaining)
        if len(replenish_intents) >= 3:
            assert replenish_intents[2].qty == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_iceberg_monitor_and_replenish_stops_when_complete() -> None:
    """Verify Iceberg stops replenishing when total quantity filled."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.5, replenish_threshold=1.0)

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)
    execution_id = intents[0].meta["execution_id"]

    # Fill exactly total quantity
    fills = [
        FillEvent(
            order_id=intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=0.5,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=25.0,
            meta=intents[0].meta.copy(),
        ),
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="BTC/USDT",
            side="buy",
            qty=0.5,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=25.0,
            meta={"execution_id": execution_id, "slice_idx": 1},
        ),
    ]

    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    with patch.object(executor, "track_fills", return_value=mock_fills()):
        replenish_intents: list[OrderIntent] = []
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents.append(intent)

        # Should generate exactly 1 replenishment (second slice)
        # Should not generate more after total filled
        assert len(replenish_intents) == 1


@pytest.mark.asyncio
async def test_iceberg_metadata_round_trip() -> None:
    """Verify OrderIntent.meta → FillEvent → replenishment round-trip for iceberg."""
    executor = IcebergExecutor(
        strategy_id="test_strat", visible_ratio=0.25, replenish_threshold=1.0
    )

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=4.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    # Plan initial execution
    intents = await executor.plan_execution(algo)
    initial_intent = intents[0]
    execution_id = initial_intent.meta["execution_id"]

    # ROUND-TRIP CYCLE: Complete chain of Intent → Fill → Intent → Fill
    # visible_qty = 4.0 * 0.25 = 1.0 per slice
    # Build complete fill chain with metadata propagation
    fills = [
        # Fill 0: From initial intent
        FillEvent(
            order_id=initial_intent.id,
            symbol=initial_intent.symbol,
            side=initial_intent.side,
            qty=1.0,  # Fill entire visible portion
            price=50000.0,
            ts_fill_ns=initial_intent.ts_local_ns + 1000,
            fee=50.0,
            meta=initial_intent.meta.copy(),  # Copy metadata from initial intent
        ),
        # Fill 1: From first replenishment (will be created dynamically)
        # This will be added after we capture the first replenishment intent
        # Fill 2: From second replenishment
        # This will be added after we capture the second replenishment intent
    ]

    # Verify metadata preserved in initial fill
    assert fills[0].meta["execution_id"] == execution_id
    assert fills[0].meta["slice_id"] == initial_intent.meta["slice_id"]
    assert fills[0].meta["slice_idx"] == 0
    assert fills[0].meta["algo_type"] == "Iceberg"
    assert fills[0].meta["total_quantity"] == 4.0
    assert fills[0].meta["visible_qty"] == pytest.approx(1.0)

    # Use generator to build fills dynamically based on replenishment intents
    replenish_intents_captured: list[OrderIntent] = []

    async def dynamic_mock_fills() -> AsyncIterator[FillEvent]:
        # Yield initial fill
        yield fills[0]

        # After yielding initial fill, we expect a replenishment intent
        # Wait for it to be captured, then yield a fill based on it
        # For testing, we'll simulate 2 replenishment cycles
        if len(replenish_intents_captured) >= 1:
            # Create fill from first replenishment intent
            yield FillEvent(
                order_id=replenish_intents_captured[0].id,
                symbol=replenish_intents_captured[0].symbol,
                side=replenish_intents_captured[0].side,
                qty=1.0,
                price=50000.0,
                ts_fill_ns=replenish_intents_captured[0].ts_local_ns + 1000,
                fee=50.0,
                meta=replenish_intents_captured[0].meta.copy(),
            )

    with patch.object(executor, "track_fills", return_value=dynamic_mock_fills()):
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents_captured.append(intent)
            # Capture first 2 replenishments
            if len(replenish_intents_captured) >= 2:
                break

    # Verify we got 2 replenishment intents
    assert len(replenish_intents_captured) >= 1

    # Verify first replenishment intent has correct metadata
    replenish_intent_1 = replenish_intents_captured[0]
    assert replenish_intent_1.meta["execution_id"] == execution_id
    assert replenish_intent_1.meta["slice_idx"] == 1
    assert replenish_intent_1.meta["slice_id"] == f"{execution_id}_slice_1"
    assert replenish_intent_1.meta["algo_type"] == "Iceberg"
    assert replenish_intent_1.meta["total_quantity"] == 4.0

    # CRITICAL: Verify metadata propagates through chain
    # OrderIntent_0 → Fill_0 → OrderIntent_1
    assert initial_intent.meta["execution_id"] == replenish_intent_1.meta["execution_id"]
    assert initial_intent.meta["algo_type"] == replenish_intent_1.meta["algo_type"]
    assert initial_intent.meta["total_quantity"] == replenish_intent_1.meta["total_quantity"]

    # Verify slice_id changes but execution_id persists
    assert initial_intent.meta["slice_id"] != replenish_intent_1.meta["slice_id"]
    assert initial_intent.meta["slice_idx"] == 0
    assert replenish_intent_1.meta["slice_idx"] == 1


@pytest.mark.asyncio
async def test_iceberg_multi_price_levels_validation() -> None:
    """Verify Iceberg validates price_levels parameter."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.2)

    # Empty list
    algo_empty = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=5.0,
        duration_seconds=3600,
        params={"price_levels": []},
    )

    with pytest.raises(ValueError, match="price_levels must not be empty"):
        await executor.plan_execution(algo_empty)

    # Not a list
    algo_not_list = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=5.0,
        duration_seconds=3600,
        params={"price_levels": "50000"},
    )

    with pytest.raises(TypeError, match="price_levels must be a list"):
        await executor.plan_execution(algo_not_list)

    # Invalid price in list
    algo_bad_price = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=5.0,
        duration_seconds=3600,
        params={"price_levels": [50000.0, 0.0, 49800.0]},
    )

    with pytest.raises(ValueError, match=r"price_levels\[1\] must be > 0"):
        await executor.plan_execution(algo_bad_price)


@pytest.mark.asyncio
async def test_iceberg_multi_price_levels_plan() -> None:
    """Verify Iceberg plans with multiple price levels."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.2)

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=3600,
        params={"price_levels": [50000.0, 49900.0, 49800.0]},
    )

    intents = await executor.plan_execution(algo)

    # Should return 1 intent (initial)
    assert len(intents) == 1

    # Initial intent should use first price level
    assert intents[0].limit_price == 50000.0

    # Metadata should include price_levels
    assert "price_levels" in intents[0].meta
    assert intents[0].meta["price_levels"] == [50000.0, 49900.0, 49800.0]
    assert intents[0].meta["visible_qty"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_iceberg_multi_price_levels_replenish_rotation() -> None:
    """Verify Iceberg rotates through price levels during replenishment."""
    executor = IcebergExecutor(
        strategy_id="test_strat", visible_ratio=0.25, replenish_threshold=1.0
    )

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=3.0,
        duration_seconds=3600,
        params={"price_levels": [50000.0, 49900.0, 49800.0]},
    )

    intents = await executor.plan_execution(algo)
    execution_id = intents[0].meta["execution_id"]

    # Simulate fills across multiple cycles
    # visible_qty = 3.0 * 0.25 = 0.75 per slice
    # We'll fill 3 cycles (0.75 * 3 = 2.25), leaving 0.75 for final slice
    fills = [
        # Cycle 0: Fill at first price level (50000)
        FillEvent(
            order_id=intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=0.75,
            price=50000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=37.5,
            meta=intents[0].meta.copy(),
        ),
        # Cycle 1: Fill at second price level (should be 49900)
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="BTC/USDT",
            side="buy",
            qty=0.75,
            price=49900.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=37.5,
            meta={"execution_id": execution_id, "slice_idx": 1, "algo_type": "Iceberg"},
        ),
        # Cycle 2: Fill at third price level (should be 49800)
        FillEvent(
            order_id=f"{execution_id}_slice_2",
            symbol="BTC/USDT",
            side="buy",
            qty=0.75,
            price=49800.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=37.5,
            meta={"execution_id": execution_id, "slice_idx": 2, "algo_type": "Iceberg"},
        ),
    ]

    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    with patch.object(executor, "track_fills", return_value=mock_fills()):
        replenish_intents: list[OrderIntent] = []
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents.append(intent)

        # Should generate 3 replenishment intents (after each of 3 fills)
        assert len(replenish_intents) == 3

        # Verify price rotation through all 3 levels
        # slice_1: index 1 % 3 = 1 → 49900
        # slice_2: index 2 % 3 = 2 → 49800
        # slice_3: index 3 % 3 = 0 → 50000 (wraps around to first level)
        assert replenish_intents[0].limit_price == 49900.0
        assert replenish_intents[1].limit_price == 49800.0
        assert replenish_intents[2].limit_price == 50000.0  # Verifies wrap-around


@pytest.mark.asyncio
async def test_iceberg_monitor_handles_out_of_order_fills() -> None:
    """Verify late fills from completed slices do not trigger extra replenishments."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.5, replenish_threshold=0.5)

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=4.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)
    initial_intent = intents[0]
    execution_id = initial_intent.meta["execution_id"]

    fill_queue: asyncio.Queue[FillEvent | None] = asyncio.Queue()

    # Initial fill fully consumes first slice (visible qty = 2.0)
    await fill_queue.put(
        FillEvent(
            order_id=initial_intent.id,
            symbol=initial_intent.symbol,
            side=initial_intent.side,
            qty=2.0,
            price=50000.0,
            ts_fill_ns=initial_intent.ts_local_ns + 1_000,
            fee=100.0,
            meta=initial_intent.meta.copy(),
        )
    )

    async def queue_fills() -> AsyncIterator[FillEvent]:
        while True:
            item = await fill_queue.get()
            if item is None:
                break
            yield item

    replenish_intents: list[OrderIntent] = []

    with patch.object(executor, "track_fills", return_value=queue_fills()):
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents.append(intent)

            if len(replenish_intents) == 1:
                # Late fill from slice 0 (should not affect slice 1 tracking)
                await fill_queue.put(
                    FillEvent(
                        order_id=initial_intent.id,
                        symbol=initial_intent.symbol,
                        side=initial_intent.side,
                        qty=0.5,
                        price=50000.0,
                        ts_fill_ns=int(time.time() * 1e9),
                        fee=25.0,
                        meta=initial_intent.meta.copy(),
                    )
                )

                # Legitimate fill for slice 1
                await fill_queue.put(
                    FillEvent(
                        order_id=intent.id,
                        symbol=intent.symbol,
                        side=intent.side,
                        qty=1.0,
                        price=50000.0,
                        ts_fill_ns=int(time.time() * 1e9),
                        fee=50.0,
                        meta=intent.meta.copy(),
                    )
                )

            elif len(replenish_intents) == 2:
                await fill_queue.put(None)
                break

    assert len(replenish_intents) == 2
    assert replenish_intents[0].meta["slice_idx"] == 1
    assert replenish_intents[1].meta["slice_idx"] == 2

    # Ensure generator is drained if loop exited without sentinel
    await fill_queue.put(None)
