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

    weights = executor._calculate_volume_profile(symbol="BTC/USDT", duration_seconds=300)

    # Should return uniform distribution
    assert len(weights) == 4
    assert all(w == pytest.approx(0.25) for w in weights)
    assert sum(weights) == pytest.approx(1.0)


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

    weights = executor._calculate_volume_profile(symbol="BTC/USDT", duration_seconds=300)

    # Should have 3 weights summing to 1.0
    assert len(weights) == 3
    assert sum(weights) == pytest.approx(1.0)

    # Middle slice should have highest weight (peak volume)
    assert weights[1] > weights[0]
    assert weights[1] > weights[2]


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

    weights = executor._calculate_volume_profile(symbol="BTC/USDT", duration_seconds=300)

    # Should fall back to uniform distribution
    assert len(weights) == 2
    assert all(w == pytest.approx(0.5) for w in weights)
    assert sum(weights) == pytest.approx(1.0)


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
