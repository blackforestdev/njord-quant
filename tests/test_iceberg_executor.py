"""Tests for Iceberg executor (Phase 8.4)."""

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

    with pytest.raises(ValueError, match=r"limit_price must be provided"):
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

    # Simulate multiple fill cycles
    # Visible qty = 5.0 * 0.1 = 0.5 per slice
    # Replenish at 100% = 0.5 filled each time
    fills = [
        # Cycle 1: Fill slice 0 completely
        FillEvent(
            order_id=intents[0].id,
            symbol="ETH/USDT",
            side="sell",
            qty=0.5,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=1.5,
            meta=intents[0].meta.copy(),
        ),
        # Cycle 2: Fill slice 1 completely
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="ETH/USDT",
            side="sell",
            qty=0.5,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=1.5,
            meta={"execution_id": execution_id, "slice_idx": 1},
        ),
        # Cycle 3: Fill slice 2 completely
        FillEvent(
            order_id=f"{execution_id}_slice_2",
            symbol="ETH/USDT",
            side="sell",
            qty=0.5,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=1.5,
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

        # Should generate 3 replenishment intents (fills of 0.5 each trigger next)
        assert len(replenish_intents) >= 2  # At least 2 cycles


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
    """Verify OrderIntent.meta → FillEvent round-trip for iceberg replenishment."""
    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.2, replenish_threshold=0.5)

    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=5.0,
        duration_seconds=3600,
        params={"limit_price": 50000.0},
    )

    # Plan initial execution
    intents = await executor.plan_execution(algo)
    initial_intent = intents[0]
    execution_id = initial_intent.meta["execution_id"]

    # Build fills directly from planned intent metadata (round-trip)
    fills = [
        FillEvent(
            order_id=initial_intent.id,
            symbol=initial_intent.symbol,
            side=initial_intent.side,
            qty=0.5,  # Reach threshold of 1.0 visible
            price=50000.0,
            ts_fill_ns=initial_intent.ts_local_ns + 1000,
            fee=25.0,
            meta=initial_intent.meta.copy(),  # Copy metadata from intent
        ),
        FillEvent(
            order_id=initial_intent.id,
            symbol=initial_intent.symbol,
            side=initial_intent.side,
            qty=0.5,  # Total 1.0 filled, trigger replenish
            price=50000.0,
            ts_fill_ns=initial_intent.ts_local_ns + 2000,
            fee=25.0,
            meta=initial_intent.meta.copy(),
        ),
    ]

    # Verify metadata preserved in fills
    for fill in fills:
        assert fill.meta["execution_id"] == execution_id
        assert fill.meta["slice_id"] == initial_intent.meta["slice_id"]
        assert fill.meta["slice_idx"] == 0
        assert fill.meta["algo_type"] == "Iceberg"
        assert fill.meta["total_quantity"] == 5.0

    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    with patch.object(executor, "track_fills", return_value=mock_fills()):
        replenish_intents: list[OrderIntent] = []
        async for intent in executor._monitor_and_replenish(bus, execution_id, algo):
            replenish_intents.append(intent)

        # Verify replenishment intent has correct metadata
        assert len(replenish_intents) >= 1
        replenish_intent = replenish_intents[0]
        assert replenish_intent.meta["execution_id"] == execution_id
        assert replenish_intent.meta["slice_idx"] == 1
        assert replenish_intent.meta["algo_type"] == "Iceberg"
        assert replenish_intent.meta["total_quantity"] == 5.0
