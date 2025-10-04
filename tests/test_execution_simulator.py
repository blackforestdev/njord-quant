"""Tests for execution simulator (Phase 8.7)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from execution.contracts import ExecutionAlgorithm
from execution.iceberg import IcebergExecutor
from execution.pov import POVExecutor
from execution.simulator import ExecutionSimulator
from execution.slippage import LinearSlippageModel, SquareRootSlippageModel
from execution.twap import TWAPExecutor
from execution.vwap import VWAPExecutor


@pytest.fixture
def sample_market_data() -> pd.DataFrame:
    """Create sample OHLCV market data for testing."""
    return pd.DataFrame(
        {
            "ts_open": [
                1000000000,
                2000000000,
                3000000000,
                4000000000,
                5000000000,
            ],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [10000.0, 12000.0, 11000.0, 13000.0, 14000.0],
        }
    )


@pytest.fixture
def mock_data_reader() -> MagicMock:
    """Create a mock DataReader for testing."""
    mock = MagicMock()
    # Mock read_ohlcv to return empty DataFrame
    mock.read_ohlcv.return_value = pd.DataFrame()
    return mock


def test_execution_simulator_initialization() -> None:
    """Test ExecutionSimulator initialization."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    assert simulator.slippage_model == slippage_model
    assert simulator.data_reader is None


def test_execution_simulator_with_data_reader() -> None:
    """Test ExecutionSimulator with data reader."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    # data_reader would be a DataReader instance in production
    data_reader = None  # Placeholder
    simulator = ExecutionSimulator(slippage_model=slippage_model, data_reader=data_reader)

    assert simulator.data_reader == data_reader


def test_simulate_execution_twap_basic(sample_market_data: pd.DataFrame) -> None:
    """Test basic TWAP execution simulation."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # Verify report structure
    assert report.symbol == "BTC/USDT"
    assert report.total_quantity == 1.0
    assert report.filled_quantity > 0
    assert report.avg_fill_price > 0
    assert report.total_fees > 0
    assert report.slices_completed > 0
    assert report.status in ["completed", "running"]


def test_simulate_execution_vwap_basic(
    sample_market_data: pd.DataFrame, mock_data_reader: MagicMock
) -> None:
    """Test basic VWAP execution simulation."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = VWAPExecutor(
        strategy_id="test_strat", data_reader=mock_data_reader, slice_count=3, order_type="market"
    )
    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=10.0,
        duration_seconds=600,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    assert report.symbol == "ETH/USDT"
    assert report.total_quantity == 10.0
    assert report.filled_quantity > 0
    assert report.status in ["completed", "running"]


def test_simulate_execution_iceberg_basic(sample_market_data: pd.DataFrame) -> None:
    """Test basic Iceberg execution simulation."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = IcebergExecutor(strategy_id="test_strat", visible_ratio=0.1, replenish_threshold=0.5)
    algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="ATOM/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": 10.0},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    assert report.symbol == "ATOM/USDT"
    assert report.total_quantity == 1.0
    assert report.filled_quantity > 0


def test_simulate_execution_pov_basic(
    sample_market_data: pd.DataFrame, mock_data_reader: MagicMock
) -> None:
    """Test basic POV execution simulation.

    Note: POV executor requires historical volume data from data_reader.
    With mocked empty data, POV won't generate slices, so we just verify
    it doesn't crash and returns a valid (empty) report.
    """
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=mock_data_reader,
        target_pov=0.1,
        min_volume_threshold=1000.0,
    )
    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="SOL/USDT",
        side="buy",
        total_quantity=5.0,
        duration_seconds=300,
        params={"avg_market_volume": 100000.0},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # With mocked empty data, POV won't generate slices
    # Just verify report structure is valid
    assert report.symbol == "SOL/USDT"
    assert report.total_quantity == 5.0
    assert report.status in ["completed", "running", "failed"]


def test_simulate_execution_slippage_applied_buy(
    sample_market_data: pd.DataFrame,
) -> None:
    """Test that slippage is applied correctly for buy orders."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.01)  # Higher impact
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=1, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=60,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # For buy orders, fill price should be higher than market price due to slippage
    # The first bar has close price of 100.5
    # With high impact coefficient (0.01) and order_size=1.0, market_volume=10000.0:
    # impact = 0.01 * (1.0/10000.0) * 100.5 = 0.001005
    # spread = 0.05025 (0.05% of 100.5)
    # total_slippage = 0.001005 + 0.05025/2 = ~0.026
    # fill_price should be around 100.5 + 0.026 = 100.526
    assert report.avg_fill_price > 100.5  # Should be higher than market close price
    assert report.avg_fill_price < 101.0  # But not by too much with small order


def test_simulate_execution_slippage_applied_sell(
    sample_market_data: pd.DataFrame,
) -> None:
    """Test that slippage is applied correctly for sell orders."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.01)  # Higher impact
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=1, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="sell",
        total_quantity=1.0,
        duration_seconds=60,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # For sell orders, fill price should be lower than market price due to slippage
    # The first bar has close price of 100.5
    # Slippage should reduce the fill price slightly
    assert report.avg_fill_price > 0
    assert report.avg_fill_price < 100.5  # Should be lower than market close price
    assert report.avg_fill_price > 100.0  # But not by too much with small order


def test_simulate_execution_different_slippage_models(
    sample_market_data: pd.DataFrame,
) -> None:
    """Test execution with different slippage models."""
    linear_model = LinearSlippageModel(impact_coefficient=0.001)
    sqrt_model = SquareRootSlippageModel(impact_coefficient=0.1)

    linear_simulator = ExecutionSimulator(slippage_model=linear_model)
    sqrt_simulator = ExecutionSimulator(slippage_model=sqrt_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    linear_report = linear_simulator.simulate_execution(executor, algo, sample_market_data)
    sqrt_report = sqrt_simulator.simulate_execution(executor, algo, sample_market_data)

    # Both should complete successfully
    assert linear_report.filled_quantity > 0
    assert sqrt_report.filled_quantity > 0

    # Different slippage models should produce different fill prices
    # (though this depends on order size and market conditions)
    assert linear_report.avg_fill_price > 0
    assert sqrt_report.avg_fill_price > 0


def test_simulate_execution_fees_calculated(sample_market_data: pd.DataFrame) -> None:
    """Test that fees are calculated for fills."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # Fees should be > 0 (0.1% of notional)
    assert report.total_fees > 0
    # Fees should be ~0.1% of total cost
    total_cost = report.filled_quantity * report.avg_fill_price
    expected_fee = total_cost * 0.001
    assert abs(report.total_fees - expected_fee) < 0.01


def test_simulate_execution_empty_market_data() -> None:
    """Test that empty market data raises error."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    empty_df = pd.DataFrame()

    with pytest.raises(ValueError, match="market_data cannot be empty"):
        simulator.simulate_execution(executor, algo, empty_df)


def test_simulate_execution_missing_required_columns() -> None:
    """Test that missing required columns raises error."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    # Missing 'volume' column
    incomplete_df = pd.DataFrame(
        {
            "ts_open": [1000000000, 2000000000],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
        }
    )

    with pytest.raises(ValueError, match="market_data missing required columns"):
        simulator.simulate_execution(executor, algo, incomplete_df)


def test_simulate_execution_multi_algo_comparison(
    sample_market_data: pd.DataFrame, mock_data_reader: MagicMock
) -> None:
    """Test comparing multiple execution algorithms."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    # TWAP
    twap_executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    twap_algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )
    twap_report = simulator.simulate_execution(twap_executor, twap_algo, sample_market_data)

    # VWAP
    vwap_executor = VWAPExecutor(
        strategy_id="test_strat", data_reader=mock_data_reader, slice_count=3, order_type="market"
    )
    vwap_algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )
    vwap_report = simulator.simulate_execution(vwap_executor, vwap_algo, sample_market_data)

    # Iceberg
    iceberg_executor = IcebergExecutor(
        strategy_id="test_strat", visible_ratio=0.2, replenish_threshold=0.5
    )
    iceberg_algo = ExecutionAlgorithm(
        algo_type="Iceberg",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"limit_price": 100.0},
    )
    iceberg_report = simulator.simulate_execution(
        iceberg_executor, iceberg_algo, sample_market_data
    )

    # All should complete
    assert twap_report.filled_quantity > 0
    assert vwap_report.filled_quantity > 0
    assert iceberg_report.filled_quantity > 0

    # All should have fees
    assert twap_report.total_fees > 0
    assert vwap_report.total_fees > 0
    assert iceberg_report.total_fees > 0

    # Can compare execution quality
    # VWAP might have different fill prices than TWAP due to volume weighting
    assert twap_report.avg_fill_price > 0
    assert vwap_report.avg_fill_price > 0
    assert iceberg_report.avg_fill_price > 0


def test_simulate_execution_report_structure(sample_market_data: pd.DataFrame) -> None:
    """Test execution report contains all required fields."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=3, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # Verify all required fields are present
    assert hasattr(report, "execution_id")
    assert hasattr(report, "symbol")
    assert hasattr(report, "total_quantity")
    assert hasattr(report, "filled_quantity")
    assert hasattr(report, "remaining_quantity")
    assert hasattr(report, "avg_fill_price")
    assert hasattr(report, "total_fees")
    assert hasattr(report, "slices_completed")
    assert hasattr(report, "slices_total")
    assert hasattr(report, "status")
    assert hasattr(report, "start_ts_ns")
    assert hasattr(report, "end_ts_ns")

    # Verify values make sense
    assert report.execution_id != ""
    assert report.symbol == "BTC/USDT"
    assert report.total_quantity == 1.0
    assert report.filled_quantity <= report.total_quantity
    assert report.remaining_quantity >= 0
    assert report.avg_fill_price > 0
    assert report.total_fees >= 0
    assert report.slices_completed > 0
    assert report.slices_total > 0
    assert report.status in ["completed", "running", "failed", "cancelled"]
    assert report.start_ts_ns > 0


def test_simulate_execution_quantity_conservation(
    sample_market_data: pd.DataFrame,
) -> None:
    """Test that filled + remaining = total quantity."""
    slippage_model = LinearSlippageModel(impact_coefficient=0.001)
    simulator = ExecutionSimulator(slippage_model=slippage_model)

    executor = TWAPExecutor(strategy_id="test_strat", slice_count=5, order_type="market")
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2.5,
        duration_seconds=300,
        params={},
    )

    report = simulator.simulate_execution(executor, algo, sample_market_data)

    # Quantity conservation
    assert abs(report.filled_quantity + report.remaining_quantity - report.total_quantity) < 1e-9
