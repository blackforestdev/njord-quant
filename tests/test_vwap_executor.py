"""Tests for VWAP executor (Phase 8.3)."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.contracts import OrderIntent
from execution.contracts import ExecutionAlgorithm
from execution.vwap import VWAPExecutor


def test_vwap_executor_valid() -> None:
    """Verify VWAPExecutor creation with valid parameters."""
    data_reader = MagicMock()
    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        lookback_days=7,
        slice_count=10,
        order_type="limit",
    )

    assert executor.strategy_id == "test_strat"
    assert executor.data_reader == data_reader
    assert executor.lookback_days == 7
    assert executor.slice_count == 10
    assert executor.order_type == "limit"


def test_vwap_executor_validation_lookback_days() -> None:
    """Verify VWAPExecutor rejects invalid lookback_days."""
    data_reader = MagicMock()

    with pytest.raises(ValueError, match="lookback_days must be > 0"):
        VWAPExecutor(strategy_id="test_strat", data_reader=data_reader, lookback_days=0)

    with pytest.raises(ValueError, match="lookback_days must be > 0"):
        VWAPExecutor(strategy_id="test_strat", data_reader=data_reader, lookback_days=-5)


def test_vwap_executor_validation_slice_count() -> None:
    """Verify VWAPExecutor rejects invalid slice_count."""
    data_reader = MagicMock()

    with pytest.raises(ValueError, match="slice_count must be > 0"):
        VWAPExecutor(strategy_id="test_strat", data_reader=data_reader, slice_count=0)

    with pytest.raises(ValueError, match="slice_count must be > 0"):
        VWAPExecutor(strategy_id="test_strat", data_reader=data_reader, slice_count=-3)


@pytest.mark.asyncio
async def test_vwap_plan_execution_basic() -> None:
    """Verify VWAP plan_execution returns correct number of intents."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # No data, falls back to uniform

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # Should return 5 intents (one per slice)
    assert len(intents) == 5

    # All intents should be OrderIntent
    assert all(isinstance(intent, OrderIntent) for intent in intents)


@pytest.mark.asyncio
async def test_vwap_plan_execution_quantity_distribution() -> None:
    """Verify VWAP distributes quantity based on volume weights."""
    data_reader = MagicMock()

    # Mock volume data with varying volumes
    df = pd.DataFrame(
        {
            "volume": [100, 200, 300, 200, 100, 150, 250, 200, 150, 100],
            "ts_open": [i * 1_000_000_000 for i in range(10)],
        }
    )
    data_reader.read_ohlcv.return_value = df

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="sell",
        total_quantity=5.0,
        duration_seconds=600,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # Total quantity should match (allowing for floating point precision)
    total_qty = sum(intent.qty for intent in intents)
    assert total_qty == pytest.approx(5.0)

    # Quantities should vary based on volume (not all equal)
    quantities = [intent.qty for intent in intents]
    assert len(set(quantities)) > 1  # Not all the same


@pytest.mark.asyncio
async def test_vwap_plan_execution_meta_packing() -> None:
    """Verify VWAP packs execution metadata into OrderIntent.meta."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # No data

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # All intents should have same execution_id
    execution_ids = {intent.meta["execution_id"] for intent in intents}
    assert len(execution_ids) == 1  # All slices share same execution_id

    execution_id = execution_ids.pop()

    # Check each slice has correct metadata
    for i, intent in enumerate(intents):
        assert intent.meta["execution_id"] == execution_id
        assert intent.meta["slice_id"] == f"{execution_id}_slice_{i}"
        assert intent.meta["algo_type"] == "VWAP"
        assert intent.meta["slice_idx"] == i
        assert "volume_weight" in intent.meta  # Should include weight
        assert isinstance(intent.meta["volume_weight"], float)


@pytest.mark.asyncio
async def test_vwap_plan_execution_order_type_market() -> None:
    """Verify VWAP creates market orders when configured."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
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
async def test_vwap_plan_execution_limit_price_missing() -> None:
    """Verify VWAP raises error when limit_price missing from params."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="limit",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
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
async def test_vwap_plan_execution_limit_price_from_params() -> None:
    """Verify VWAP pulls limit_price from algo.params when provided."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="limit",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": 50000.0},  # Specify limit price in params
    )

    intents = await executor.plan_execution(algo)

    # All intents should use the limit_price from params
    for intent in intents:
        assert intent.type == "limit"
        assert intent.limit_price == 50000.0


@pytest.mark.asyncio
async def test_vwap_volume_profile_uniform_fallback() -> None:
    """Verify VWAP falls back to uniform distribution when data unavailable."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # No data available

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=4,
        order_type="market",
    )

    weights, benchmark_vwap = executor._calculate_volume_profile(
        symbol="BTC/USDT", duration_seconds=300
    )

    # Should return uniform distribution
    assert len(weights) == 4
    assert all(w == pytest.approx(0.25) for w in weights)
    assert sum(weights) == pytest.approx(1.0)
    # benchmark_vwap should be None (no data)
    assert benchmark_vwap is None


@pytest.mark.asyncio
async def test_vwap_volume_profile_from_data() -> None:
    """Verify VWAP calculates volume profile from historical data."""
    data_reader = MagicMock()

    # Mock volume data with pattern: low-high-low
    df = pd.DataFrame(
        {
            "volume": [100, 100, 300, 300, 100, 100],  # Peak in middle
            "ts_open": [i * 1_000_000_000 for i in range(6)],
        }
    )
    data_reader.read_ohlcv.return_value = df

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="market",
    )

    weights, benchmark_vwap = executor._calculate_volume_profile(
        symbol="BTC/USDT", duration_seconds=300
    )

    # Should have 3 weights summing to 1.0
    assert len(weights) == 3
    assert sum(weights) == pytest.approx(1.0)

    # Middle slice should have highest weight (peak volume)
    assert weights[1] > weights[0]
    assert weights[1] > weights[2]

    # benchmark_vwap should be None (no price data in this mock)
    assert benchmark_vwap is None


@pytest.mark.asyncio
async def test_vwap_volume_profile_zero_volume_fallback() -> None:
    """Verify VWAP handles zero volume data gracefully."""
    data_reader = MagicMock()

    # Mock data with zero volumes
    df = pd.DataFrame({"volume": [0, 0, 0, 0], "ts_open": [i * 1_000_000_000 for i in range(4)]})
    data_reader.read_ohlcv.return_value = df

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=2,
        order_type="market",
    )

    weights, benchmark_vwap = executor._calculate_volume_profile(
        symbol="BTC/USDT", duration_seconds=300
    )

    # Should fall back to uniform distribution
    assert len(weights) == 2
    assert all(w == pytest.approx(0.5) for w in weights)
    assert sum(weights) == pytest.approx(1.0)
    # benchmark_vwap should be None (zero volume)
    assert benchmark_vwap is None


@pytest.mark.asyncio
async def test_vwap_intent_id_matches_slice_id() -> None:
    """Verify OrderIntent.id matches slice_id for tracking."""
    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # Verify intent.id matches meta.slice_id for fill tracking
    for intent in intents:
        assert intent.id == intent.meta["slice_id"]


@pytest.mark.asyncio
async def test_vwap_meta_fillev_round_trip() -> None:
    """Verify OrderIntent.meta → FillEvent round-trip integrity.

    Tests that all metadata fields (execution_id, slice_id, algo_type,
    volume_weight, benchmark_vwap) are preserved when constructing a
    FillEvent from an OrderIntent.
    """
    from core.contracts import FillEvent

    data_reader = MagicMock()
    # Mock volume data so we get a known benchmark VWAP
    df = pd.DataFrame(
        {
            "volume": [100, 200, 300],
            "high": [50000, 51000, 52000],
            "low": [49000, 50000, 51000],
            "close": [49500, 50500, 51500],
            "ts_open": [i * 1_000_000_000 for i in range(3)],
        }
    )
    data_reader.read_ohlcv.return_value = df

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    intents = await executor.plan_execution(algo)

    # Take first intent and construct FillEvent from it
    intent = intents[0]
    fill = FillEvent(
        order_id=intent.id,  # Use intent.id as order_id
        symbol=intent.symbol,
        side=intent.side,
        qty=intent.qty,
        price=50000.0,  # Simulated fill price
        ts_fill_ns=intent.ts_local_ns + 1000,  # Filled shortly after
        fee=5.0,
        meta=intent.meta.copy(),  # Copy meta from intent
    )

    # Verify round-trip: all meta fields preserved
    assert fill.meta["execution_id"] == intent.meta["execution_id"]
    assert fill.meta["slice_id"] == intent.meta["slice_id"]
    assert fill.meta["algo_type"] == intent.meta["algo_type"]
    assert fill.meta["slice_idx"] == intent.meta["slice_idx"]
    assert fill.meta["volume_weight"] == intent.meta["volume_weight"]
    assert fill.meta["benchmark_vwap"] == intent.meta["benchmark_vwap"]

    # Verify algo_type is "VWAP"
    assert fill.meta["algo_type"] == "VWAP"

    # Verify execution_id starts with "vwap_"
    assert fill.meta["execution_id"].startswith("vwap_")

    # Verify volume_weight is a float
    assert isinstance(fill.meta["volume_weight"], float)

    # Verify benchmark_vwap is present (may be None or float)
    assert "benchmark_vwap" in fill.meta


@pytest.mark.asyncio
async def test_vwap_benchmark_calculation() -> None:
    """Verify VWAP benchmark is calculated correctly from historical data."""
    data_reader = MagicMock()

    # Mock OHLCV data with known prices and volumes
    df = pd.DataFrame(
        {
            "volume": [100, 200, 300],  # Total volume: 600
            "high": [102, 104, 106],
            "low": [98, 96, 94],
            "close": [100, 100, 100],
            "ts_open": [i * 1_000_000_000 for i in range(3)],
        }
    )
    data_reader.read_ohlcv.return_value = df

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="market",
    )

    _weights, benchmark_vwap = executor._calculate_volume_profile(
        symbol="BTC/USDT", duration_seconds=300
    )

    # Typical price = (high + low + close) / 3
    # Slice 0: (102 + 98 + 100) / 3 = 100.0, volume=100
    # Slice 1: (104 + 96 + 100) / 3 = 100.0, volume=200
    # Slice 2: (106 + 94 + 100) / 3 = 100.0, volume=300
    # Benchmark VWAP = (100*100 + 100*200 + 100*300) / 600 = 60000 / 600 = 100.0

    assert benchmark_vwap is not None
    assert benchmark_vwap == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_vwap_monitor_fills_with_benchmark() -> None:
    """Verify _monitor_fills tracks execution VWAP vs benchmark."""
    import time
    from collections.abc import AsyncIterator
    from unittest.mock import patch

    from core.contracts import FillEvent

    data_reader = MagicMock()
    executor = VWAPExecutor(
        strategy_id="test_strat", data_reader=data_reader, slice_count=3, order_type="market"
    )

    # Mock bus
    bus = MagicMock()

    # Create mock fills with known prices
    execution_id = "vwap_test123"
    benchmark_vwap = 50000.0  # Benchmark VWAP

    fills = [
        FillEvent(
            order_id=f"{execution_id}_slice_0",
            symbol="BTC/USDT",
            side="buy",
            qty=0.3,
            price=49000.0,  # Below benchmark
            ts_fill_ns=int(time.time() * 1e9),
            fee=3.0,
            meta={"execution_id": execution_id, "slice_id": f"{execution_id}_slice_0"},
        ),
        FillEvent(
            order_id=f"{execution_id}_slice_1",
            symbol="BTC/USDT",
            side="buy",
            qty=0.4,
            price=50000.0,  # At benchmark
            ts_fill_ns=int(time.time() * 1e9),
            fee=4.0,
            meta={"execution_id": execution_id, "slice_id": f"{execution_id}_slice_1"},
        ),
        FillEvent(
            order_id=f"{execution_id}_slice_2",
            symbol="BTC/USDT",
            side="buy",
            qty=0.3,
            price=52000.0,  # Above benchmark
            ts_fill_ns=int(time.time() * 1e9),
            fee=3.0,
            meta={"execution_id": execution_id, "slice_id": f"{execution_id}_slice_2"},
        ),
    ]

    # Mock async generator for fills
    async def mock_fills() -> AsyncIterator[FillEvent]:
        for fill in fills:
            yield fill

    # Patch track_fills to return our mock fills
    with patch.object(executor, "track_fills", return_value=mock_fills()):
        # Monitor fills with benchmark
        report = await executor._monitor_fills(
            bus=bus,
            execution_id=execution_id,
            total_quantity=1.0,
            symbol="BTC/USDT",
            benchmark_vwap=benchmark_vwap,
        )

        # Execution VWAP = (49000*0.3 + 50000*0.4 + 52000*0.3) / 1.0 = 50300
        expected_execution_vwap = (49000 * 0.3 + 50000 * 0.4 + 52000 * 0.3) / 1.0

        # Verify report
        assert report.benchmark_vwap == benchmark_vwap
        assert report.avg_fill_price == pytest.approx(expected_execution_vwap)

        # VWAP deviation = (50300 - 50000) / 50000 = 0.006 (0.6%)
        expected_deviation = (expected_execution_vwap - benchmark_vwap) / benchmark_vwap
        assert report.vwap_deviation == pytest.approx(expected_deviation)


def test_vwap_recalculate_remaining_weights_no_divergence() -> None:
    """Verify recalculate_remaining_weights keeps original weights if no divergence."""
    data_reader = MagicMock()
    executor = VWAPExecutor(
        strategy_id="test_strat", data_reader=data_reader, slice_count=5, order_type="market"
    )

    # Total quantity: 10.0
    total_quantity = 10.0

    # Original weights: [0.1, 0.2, 0.3, 0.2, 0.2]
    original_weights = [0.1, 0.2, 0.3, 0.2, 0.2]

    # Fills for first 2 slices match expected
    # Expected: 0.1 * 10 = 1.0, 0.2 * 10 = 2.0
    # Actual: exactly matches expected
    fills_per_slice = {0: 1.0, 1: 2.0}

    # Recalculate from slice 2 onwards
    remaining_weights = executor.recalculate_remaining_weights(
        original_weights=original_weights,
        fills_per_slice=fills_per_slice,
        current_slice_idx=2,
        total_quantity=total_quantity,
    )

    # No divergence, so weights [0.3, 0.2, 0.2] normalized
    # Total = 0.7, so normalized: [0.3/0.7, 0.2/0.7, 0.2/0.7]
    expected = [0.3 / 0.7, 0.2 / 0.7, 0.2 / 0.7]

    assert len(remaining_weights) == 3
    for i, w in enumerate(remaining_weights):
        assert w == pytest.approx(expected[i])


def test_vwap_recalculate_remaining_weights_with_divergence() -> None:
    """Verify recalculate_remaining_weights adjusts when divergence exceeds threshold."""
    data_reader = MagicMock()
    executor = VWAPExecutor(
        strategy_id="test_strat", data_reader=data_reader, slice_count=5, order_type="market"
    )

    # Total quantity: 10.0
    total_quantity = 10.0

    # Original weights: [0.1, 0.2, 0.3, 0.2, 0.2]
    original_weights = [0.1, 0.2, 0.3, 0.2, 0.2]

    # Expected cumulative at slice 2: (0.1 + 0.2) * 10 = 3.0
    # Actual fills only 1.5 (50% of expected - significant divergence)
    fills_per_slice = {0: 0.5, 1: 1.0}

    # Recalculate from slice 2 onwards
    remaining_weights = executor.recalculate_remaining_weights(
        original_weights=original_weights,
        fills_per_slice=fills_per_slice,
        current_slice_idx=2,
        total_quantity=total_quantity,
    )

    # Actual cumulative = 1.5 / 10 = 0.15
    # Expected cumulative = 0.3
    # Divergence = |0.15 - 0.3| / 0.3 = 0.5 (50%) > 10% threshold
    # Should rebalance: take remaining weights [0.3, 0.2, 0.2], normalize
    expected = [0.3 / 0.7, 0.2 / 0.7, 0.2 / 0.7]

    assert len(remaining_weights) == 3
    for i, w in enumerate(remaining_weights):
        assert w == pytest.approx(expected[i])


@pytest.mark.asyncio
async def test_vwap_replan_remaining_slices_no_divergence() -> None:
    """Verify replan_remaining_slices maintains plan when no divergence."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # Uniform weights

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=500,
        params={},
    )

    # Get original plan
    original_intents = await executor.plan_execution(algo)

    # Simulate fills for first 2 slices that match expected quantities
    execution_id = original_intents[0].meta["execution_id"]
    fills = [
        FillEvent(
            order_id=original_intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=2.0,  # Uniform: 10 / 5 = 2.0
            price=50000.0,
            ts_fill_ns=original_intents[0].ts_local_ns,
            fee=1.0,
            meta=original_intents[0].meta,
        ),
        FillEvent(
            order_id=original_intents[1].id,
            symbol="BTC/USDT",
            side="buy",
            qty=2.0,  # Uniform: 10 / 5 = 2.0
            price=50100.0,
            ts_fill_ns=original_intents[1].ts_local_ns,
            fee=1.0,
            meta=original_intents[1].meta,
        ),
    ]

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # Should have 3 remaining slices (slices 2, 3, 4)
    assert len(adjusted_intents) == 3

    # No divergence, so quantities should still be uniform
    # Remaining quantity = 10 - 4 = 6.0
    # Uniform across 3 slices = 2.0 each
    for intent in adjusted_intents:
        assert intent.qty == pytest.approx(2.0)
        assert intent.symbol == "BTC/USDT"
        assert intent.side == "buy"
        assert intent.meta["execution_id"] == execution_id
        assert intent.meta["replanned"] is True


@pytest.mark.asyncio
async def test_vwap_replan_remaining_slices_with_divergence() -> None:
    """Verify replan_remaining_slices adjusts when fills diverge from expected."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # Uniform weights

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=10.0,
        duration_seconds=500,
        params={},
    )

    # Get original plan (uniform: 2.0 per slice)
    original_intents = await executor.plan_execution(algo)

    # Simulate fills for first 2 slices with SIGNIFICANT divergence
    fills = [
        FillEvent(
            order_id=original_intents[0].id,
            symbol="ETH/USDT",
            side="sell",
            qty=0.8,  # Only 40% of expected (2.0 expected, 0.8 actual)
            price=3000.0,
            ts_fill_ns=original_intents[0].ts_local_ns,
            fee=0.5,
            meta=original_intents[0].meta,
        ),
        FillEvent(
            order_id=original_intents[1].id,
            symbol="ETH/USDT",
            side="sell",
            qty=1.2,  # 60% of expected (2.0 expected, 1.2 actual)
            price=3010.0,
            ts_fill_ns=original_intents[1].ts_local_ns,
            fee=0.6,
            meta=original_intents[1].meta,
        ),
    ]

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # Slice 0: 0.8/2.0 = 40% filled (PARTIAL - first incomplete)
    # Slice 1: 1.2/2.0 = 60% filled (PARTIAL)
    # Slices 2-4: 0% filled
    # Replan starts from slice 0 (first incomplete), so 5 slices
    assert len(adjusted_intents) == 5

    # Actual fills = 0.8 + 1.2 = 2.0
    # Remaining quantity = 10 - 2.0 = 8.0
    total_remaining_qty = sum(intent.qty for intent in adjusted_intents)
    assert total_remaining_qty == pytest.approx(8.0)

    # First replanned intent should be for slice 0
    assert adjusted_intents[0].meta["slice_idx"] == 0

    # All should be marked as replanned
    for intent in adjusted_intents:
        assert intent.meta["replanned"] is True


@pytest.mark.asyncio
async def test_vwap_replan_remaining_slices_preserves_metadata() -> None:
    """Verify replan_remaining_slices preserves critical metadata fields."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    # Mock volume data for non-uniform weights
    df = pd.DataFrame(
        {
            "volume": [100, 200, 300, 200, 100],  # Peak in middle
            "high": [50000, 51000, 52000, 51000, 50000],
            "low": [49000, 50000, 51000, 50000, 49000],
            "close": [49500, 50500, 51500, 50500, 49500],
            "ts_open": [i * 1_000_000_000 for i in range(5)],
        }
    )
    data_reader.read_ohlcv.return_value = df

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="limit",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=5.0,
        duration_seconds=500,
        params={"limit_price": 50000.0},
    )

    # Get original plan
    original_intents = await executor.plan_execution(algo)

    # Capture original benchmark_vwap
    original_benchmark = original_intents[0].meta["benchmark_vwap"]

    # Simulate fill for first slice only
    fills = [
        FillEvent(
            order_id=original_intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=original_intents[0].qty,
            price=50000.0,
            ts_fill_ns=original_intents[0].ts_local_ns,
            fee=5.0,
            meta=original_intents[0].meta,
        ),
    ]

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # Verify metadata preserved
    execution_id = original_intents[0].meta["execution_id"]
    for intent in adjusted_intents:
        assert intent.meta["execution_id"] == execution_id
        assert intent.meta["algo_type"] == "VWAP"
        assert intent.meta["benchmark_vwap"] == original_benchmark
        assert "volume_weight" in intent.meta
        assert "slice_id" in intent.meta
        assert "slice_idx" in intent.meta
        assert intent.meta["replanned"] is True

    # Verify limit price preserved
    for intent in adjusted_intents:
        assert intent.limit_price == 50000.0


@pytest.mark.asyncio
async def test_vwap_replan_partial_fill_single_slice() -> None:
    """Verify replan handles single slice with partial fill correctly."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # Uniform weights

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=500,
        params={},
    )

    # Get original plan (uniform: 2.0 per slice)
    original_intents = await executor.plan_execution(algo)

    # Simulate partial fill for first slice only (1.0 out of 2.0)
    fills = [
        FillEvent(
            order_id=original_intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=1.0,  # PARTIAL: 50% of planned 2.0
            price=50000.0,
            ts_fill_ns=original_intents[0].ts_local_ns,
            fee=0.5,
            meta=original_intents[0].meta,
        ),
    ]

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # Should replan from slice 0 (partially filled) through slice 4
    # Remaining quantity = 10 - 1 = 9.0
    assert len(adjusted_intents) == 5

    total_adjusted_qty = sum(intent.qty for intent in adjusted_intents)
    assert total_adjusted_qty == pytest.approx(9.0)

    # First intent should be for slice 0 (to complete it)
    assert adjusted_intents[0].meta["slice_idx"] == 0


@pytest.mark.asyncio
async def test_vwap_replan_partial_fills_multiple_slices() -> None:
    """Verify replan handles multiple slices with varying partial fills."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # Uniform weights

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=10.0,
        duration_seconds=500,
        params={},
    )

    # Get original plan (uniform: 2.0 per slice)
    original_intents = await executor.plan_execution(algo)

    # Simulate varying partial fills:
    # Slice 0: 100% filled (2.0/2.0)
    # Slice 1: 75% filled (1.5/2.0)
    # Slice 2: 50% filled (1.0/2.0)
    # Slice 3: 0% filled (0/2.0)
    # Slice 4: 0% filled (0/2.0)
    fills = [
        FillEvent(
            order_id=original_intents[0].id,
            symbol="BTC/USDT",
            side="buy",
            qty=2.0,  # FULL
            price=50000.0,
            ts_fill_ns=original_intents[0].ts_local_ns,
            fee=1.0,
            meta=original_intents[0].meta,
        ),
        FillEvent(
            order_id=original_intents[1].id,
            symbol="BTC/USDT",
            side="buy",
            qty=1.5,  # PARTIAL: 75%
            price=50100.0,
            ts_fill_ns=original_intents[1].ts_local_ns,
            fee=0.75,
            meta=original_intents[1].meta,
        ),
        FillEvent(
            order_id=original_intents[2].id,
            symbol="BTC/USDT",
            side="buy",
            qty=1.0,  # PARTIAL: 50%
            price=50200.0,
            ts_fill_ns=original_intents[2].ts_local_ns,
            fee=0.5,
            meta=original_intents[2].meta,
        ),
    ]

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # Should replan from slice 1 (first partial) onwards
    # Remaining quantity = 10 - 4.5 = 5.5
    assert len(adjusted_intents) == 4  # Slices 1, 2, 3, 4

    total_adjusted_qty = sum(intent.qty for intent in adjusted_intents)
    assert total_adjusted_qty == pytest.approx(5.5)

    # First replanned intent should be for slice 1
    assert adjusted_intents[0].meta["slice_idx"] == 1


@pytest.mark.asyncio
async def test_vwap_replan_all_slices_partially_filled() -> None:
    """Verify replan handles case where ALL slices are partially filled."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # Uniform weights

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="sell",
        total_quantity=10.0,
        duration_seconds=500,
        params={},
    )

    # Get original plan (uniform: 2.0 per slice)
    original_intents = await executor.plan_execution(algo)

    # ALL slices get 50% partial fills
    fills = []
    for i in range(5):
        fills.append(
            FillEvent(
                order_id=original_intents[i].id,
                symbol="BTC/USDT",
                side="sell",
                qty=1.0,  # PARTIAL: 50% of 2.0
                price=50000.0 + i * 100,
                ts_fill_ns=original_intents[i].ts_local_ns,
                fee=0.5,
                meta=original_intents[i].meta,
            )
        )

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # All slices partially filled (50% each)
    # First incomplete slice is slice 0
    # Remaining quantity = 10 - 5 = 5.0
    # Should NOT return empty list - this was the bug
    assert len(adjusted_intents) == 5

    total_adjusted_qty = sum(intent.qty for intent in adjusted_intents)
    assert total_adjusted_qty == pytest.approx(5.0)

    # All intents should be marked as replanned
    for intent in adjusted_intents:
        assert intent.meta["replanned"] is True

    # First replanned intent should be for slice 0 (first incomplete)
    assert adjusted_intents[0].meta["slice_idx"] == 0


@pytest.mark.asyncio
async def test_vwap_replan_all_slices_fully_filled_with_residual() -> None:
    """Verify replan creates residual slices when all original slices filled but quantity remains."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None  # Uniform weights

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=5,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="sell",
        total_quantity=12.0,  # 12.0 total, but slices only cover 10.0
        duration_seconds=500,
        params={},
    )

    # Get original plan (uniform: 2.4 per slice for 12.0 total)
    original_intents = await executor.plan_execution(algo)

    # All slices get FULLY filled (100% of their planned qty)
    # But total planned was only 12.0, so we'll simulate 10.0 filled
    fills = []
    for i in range(5):
        fills.append(
            FillEvent(
                order_id=original_intents[i].id,
                symbol="BTC/USDT",
                side="sell",
                qty=2.0,  # 2.0 each (vs planned 2.4)
                price=50000.0 + i * 100,
                ts_fill_ns=original_intents[i].ts_local_ns,
                fee=1.0,
                meta=original_intents[i].meta,
            )
        )

    # Replan remaining slices
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    # All slices partially filled but significant quantity remains
    # Should replan from first incomplete (slice 0)
    assert len(adjusted_intents) > 0

    # Remaining quantity = 12 - 10 = 2.0
    total_adjusted_qty = sum(intent.qty for intent in adjusted_intents)
    assert total_adjusted_qty == pytest.approx(2.0)

    # All intents should be marked as replanned
    for intent in adjusted_intents:
        assert intent.meta["replanned"] is True


@pytest.mark.asyncio
async def test_vwap_replan_no_remaining_quantity() -> None:
    """Verify replan returns empty when execution fully complete."""
    from core.contracts import FillEvent

    data_reader = MagicMock()
    data_reader.read_ohlcv.return_value = None

    executor = VWAPExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,
        slice_count=3,
        order_type="market",
    )

    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=6.0,
        duration_seconds=300,
        params={},
    )

    original_intents = await executor.plan_execution(algo)

    # All slices fully filled
    fills = [
        FillEvent(
            order_id=intent.id,
            symbol="BTC/USDT",
            side="buy",
            qty=intent.qty,  # FULL quantity
            price=50000.0,
            ts_fill_ns=intent.ts_local_ns,
            fee=1.0,
            meta=intent.meta,
        )
        for intent in original_intents
    ]

    # Replan should return empty - nothing left to execute
    adjusted_intents = await executor.replan_remaining_slices(
        original_intents=original_intents, fills=fills, algo=algo
    )

    assert len(adjusted_intents) == 0
