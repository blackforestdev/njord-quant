"""Tests for TWAP executor (Phase 8.2)."""

import time
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from core.contracts import FillEvent, OrderIntent
from execution.contracts import ExecutionAlgorithm
from execution.twap import TWAPExecutor


def test_twap_executor_valid() -> None:
    """Verify TWAPExecutor creation with valid parameters."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=10, order_type="limit")

    assert executor.strategy_id == "test_strat"
    assert executor.slice_count == 10
    assert executor.order_type == "limit"


def test_twap_executor_validation_slice_count() -> None:
    """Verify TWAPExecutor rejects invalid slice_count."""
    with pytest.raises(ValueError, match="slice_count must be > 0"):
        TWAPExecutor(strategy_id="test_strat", slice_count=0)

    with pytest.raises(ValueError, match="slice_count must be > 0"):
        TWAPExecutor(strategy_id="test_strat", slice_count=-5)


@pytest.mark.asyncio
async def test_twap_plan_execution_basic() -> None:
    """Verify TWAP plan_execution returns correct number of intents."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=5, order_type="market")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # Should return 10 intents total (5 execution + 5 cancel)
    assert len(intents) == 10

    # All intents should be OrderIntent
    assert all(isinstance(intent, OrderIntent) for intent in intents)

    # Verify split
    execution_intents = [intent for intent in intents if intent.qty > 0]
    cancel_intents = [intent for intent in intents if intent.qty == 0]
    assert len(execution_intents) == 5
    assert len(cancel_intents) == 5

    for i, cancel_intent in enumerate(cancel_intents):
        assert cancel_intent.qty == 0.0
        assert cancel_intent.meta["action"] == "cancel"
        assert cancel_intent.meta["slice_idx"] == i
        assert cancel_intent.meta["execution_id"] == execution_intents[i].meta["execution_id"]
        assert cancel_intent.meta["target_slice_id"] == execution_intents[i].meta["slice_id"]


@pytest.mark.asyncio
async def test_twap_plan_execution_quantity_distribution() -> None:
    """Verify TWAP distributes quantity evenly across slices."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=10, order_type="market")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=5.0,
        duration_seconds=600,
        params={},
    )

    intents = await executor.plan_execution(algo)

    execution_intents = [intent for intent in intents if intent.qty > 0]

    # Each execution slice should have equal quantity
    expected_qty = 5.0 / 10  # 0.5
    for intent in execution_intents:
        assert intent.qty == pytest.approx(expected_qty)

    # Total quantity should match
    total_qty = sum(intent.qty for intent in execution_intents)
    assert total_qty == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_twap_plan_execution_scheduling() -> None:
    """Verify TWAP schedules slices at correct intervals."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=4, order_type="market")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=400,  # 400 seconds
        params={},
    )

    intents = await executor.plan_execution(algo)

    execution_intents = [intent for intent in intents if intent.qty > 0]
    cancel_intents = [intent for intent in intents if intent.qty == 0]

    # Expected interval: 400 seconds / 4 slices = 100 seconds = 100_000_000_000 ns
    expected_interval_ns = 100_000_000_000

    # Check intervals between consecutive execution slices
    for i in range(len(execution_intents) - 1):
        interval = execution_intents[i + 1].ts_local_ns - execution_intents[i].ts_local_ns
        assert interval == expected_interval_ns

    cancel_timestamps = {cancel.ts_local_ns for cancel in cancel_intents}
    assert len(cancel_timestamps) == 1
    cancel_ts = cancel_timestamps.pop()
    assert cancel_ts - execution_intents[0].ts_local_ns == expected_interval_ns * len(
        execution_intents
    )


@pytest.mark.asyncio
async def test_twap_plan_execution_meta_packing() -> None:
    """Verify TWAP packs execution metadata into OrderIntent.meta."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="limit")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": 50000.0},  # Required for limit orders
    )

    intents = await executor.plan_execution(algo)

    execution_intents = [intent for intent in intents if intent.qty > 0]

    # All intents should have same execution_id
    execution_ids = {intent.meta["execution_id"] for intent in execution_intents}
    assert len(execution_ids) == 1  # All slices share same execution_id

    execution_id = execution_ids.pop()

    # Check each slice has correct metadata
    for i, intent in enumerate(execution_intents):
        assert intent.meta["execution_id"] == execution_id
        assert intent.meta["slice_id"] == f"{execution_id}_slice_{i}"
        assert intent.meta["algo_type"] == "TWAP"
        assert intent.meta["slice_idx"] == i


@pytest.mark.asyncio
async def test_twap_plan_execution_order_type_market() -> None:
    """Verify TWAP creates market orders when configured."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=5, order_type="market")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # All intents should be market orders
    for intent in intents:
        assert intent.type == "market"
        assert intent.limit_price is None


@pytest.mark.asyncio
async def test_twap_plan_execution_order_type_limit_missing_price() -> None:
    """Verify TWAP raises error when limit_price missing from params."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=5, order_type="limit")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},  # Missing limit_price
    )

    # Should raise ValueError when limit_price not provided
    with pytest.raises(ValueError, match=r"limit_price must be provided in algo\.params"):
        await executor.plan_execution(algo)


@pytest.mark.asyncio
async def test_twap_plan_execution_limit_price_invalid() -> None:
    """Verify TWAP raises error when limit_price is invalid."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="limit")

    # Test zero price
    algo_zero = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": 0.0},
    )

    with pytest.raises(ValueError, match="limit_price must be > 0"):
        await executor.plan_execution(algo_zero)

    # Test negative price
    algo_negative = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": -100.0},
    )

    with pytest.raises(ValueError, match="limit_price must be > 0"):
        await executor.plan_execution(algo_negative)

    # Test invalid type (string)
    algo_string = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": "50000"},  # String instead of number
    )

    with pytest.raises(TypeError, match="limit_price must be a number"):
        await executor.plan_execution(algo_string)


@pytest.mark.asyncio
async def test_twap_plan_execution_limit_price_from_params() -> None:
    """Verify TWAP pulls limit_price from algo.params when provided."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="limit")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": 50000.0},  # Specify limit price in params
    )

    intents = await executor.plan_execution(algo)

    execution_intents = [intent for intent in intents if intent.qty > 0]

    # All execution intents should use the limit_price from params
    for intent in execution_intents:
        assert intent.type == "limit"
        assert intent.limit_price == 50000.0


@pytest.mark.asyncio
async def test_twap_plan_execution_intent_attributes() -> None:
    """Verify TWAP creates OrderIntents with correct attributes."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=3.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    execution_intents = [intent for intent in intents if intent.qty > 0]

    for intent in execution_intents:
        assert intent.strategy_id == "test_strat"
        assert intent.symbol == "ETH/USDT"
        assert intent.side == "sell"
        assert intent.qty == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_twap_monitor_fills_complete() -> None:
    """Verify TWAP _monitor_fills builds correct ExecutionReport."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")

    # Mock bus
    bus = MagicMock()

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.5,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)
    execution_intents = [intent for intent in intents if intent.qty > 0]
    execution_id = execution_intents[0].meta["execution_id"]

    # Build fills directly from planned intents to verify metadata round-trip
    fills: list[FillEvent] = []
    for idx, intent in enumerate(execution_intents):
        meta = intent.meta.copy()
        fills.append(
            FillEvent(
                order_id=intent.id,
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                price=50_000.0 + idx * 100.0,
                ts_fill_ns=intent.ts_local_ns + 1_000,
                fee=7.5,
                meta=meta,
            )
        )
        # Metadata should contain identifiers for round-trip tracking
        assert meta["execution_id"] == intent.meta["execution_id"]
        assert meta["slice_id"] == intent.meta["slice_id"]
        assert meta["slice_idx"] == intent.meta["slice_idx"]

    # Mock async generator for fills
    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    # Patch track_fills to return our mock fills
    with patch.object(executor, "track_fills", return_value=mock_fills()):
        # Monitor fills
        report = await executor._monitor_fills(
            bus=bus,
            execution_id=execution_id,
            total_quantity=algo.total_quantity,
            symbol=algo.symbol,
        )

        # Verify report
        assert report.execution_id == execution_id
        assert report.symbol == "BTC/USDT"
        assert report.total_quantity == algo.total_quantity
        assert report.filled_quantity == algo.total_quantity
        assert report.remaining_quantity == 0.0
        assert report.avg_fill_price == pytest.approx(50100.0)  # Weighted average
        assert report.total_fees == 22.5
        assert report.slices_completed == 3
        assert report.slices_total == 3
        assert report.status == "completed"
        assert report.end_ts_ns is not None


@pytest.mark.asyncio
async def test_twap_monitor_fills_partial() -> None:
    """Verify TWAP _monitor_fills handles partial fills correctly."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=5, order_type="market")

    # Mock bus
    bus = MagicMock()

    # Create partial fills (only 2 out of 5 slices filled)
    execution_id = "twap_partial"
    fills = [
        FillEvent(
            order_id=f"{execution_id}_slice_0",
            symbol="ETH/USDT",
            side="sell",
            qty=1.0,
            price=3000.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=3.0,
            meta={"execution_id": execution_id, "slice_id": f"{execution_id}_slice_0"},
        ),
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="ETH/USDT",
            side="sell",
            qty=1.0,
            price=3010.0,
            ts_fill_ns=int(time.time() * 1e9),
            fee=3.0,
            meta={"execution_id": execution_id, "slice_id": f"{execution_id}_slice_1"},
        ),
    ]

    # Mock async generator for partial fills
    async def mock_partial_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill
        # Simulate timeout/no more fills
        return

    # Patch track_fills
    with patch.object(executor, "track_fills", return_value=mock_partial_fills()):
        # Monitor fills (total quantity 5.0, but only 2.0 filled)
        report = await executor._monitor_fills(
            bus=bus,
            execution_id=execution_id,
            total_quantity=5.0,
            symbol="ETH/USDT",
        )

        # Verify partial fill report
        assert report.execution_id == execution_id
        assert report.filled_quantity == 2.0
        assert report.remaining_quantity == 3.0
        assert report.avg_fill_price == pytest.approx(3005.0)
        assert report.total_fees == 6.0
        assert report.slices_completed == 2
        assert report.slices_total == 5
        assert report.status == "running"  # Not completed
        assert report.end_ts_ns is None  # Still running


@pytest.mark.asyncio
async def test_twap_intent_id_matches_slice_id() -> None:
    """Verify OrderIntent.id matches slice_id for tracking."""
    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")

    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # Filter out cancel intents (qty=0) for this test
    execution_intents = [intent for intent in intents if intent.qty > 0]

    # Verify intent.id matches meta.slice_id for fill tracking
    for intent in execution_intents:
        assert intent.id == intent.meta["slice_id"]
