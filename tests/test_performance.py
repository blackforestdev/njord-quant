"""Tests for performance analytics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from research.performance import PerformanceAnalyzer
else:
    pd = pytest.importorskip("pandas")
    from research.performance import PerformanceAnalyzer


@pytest.fixture
def sample_fills_df() -> pd.DataFrame:
    """Create sample fills DataFrame."""
    data = {
        "ts_fill_ns": [
            1704067200000000000,  # 2024-01-01 00:00
            1704153600000000000,  # 2024-01-02 00:00
            1704240000000000000,  # 2024-01-03 00:00
            1704326400000000000,  # 2024-01-04 00:00
            1704412800000000000,  # 2024-01-05 00:00
        ],
        "qty": [10.0, -5.0, 8.0, -10.0, 15.0],
        "price": [100.0, 105.0, 102.0, 108.0, 110.0],
        "realized_pnl": [50.0, 25.0, -10.0, 80.0, 30.0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_positions_df() -> pd.DataFrame:
    """Create sample positions DataFrame."""
    data = {
        "ts_ns": [
            1704067200000000000,  # 2024-01-01 00:00
            1704153600000000000,  # 2024-01-02 00:00
            1704240000000000000,  # 2024-01-03 00:00
            1704326400000000000,  # 2024-01-04 00:00
            1704412800000000000,  # 2024-01-05 00:00
        ],
        "total_equity": [100000.0, 102000.0, 101000.0, 103000.0, 105000.0],
        "cash": [50000.0, 51000.0, 50500.0, 51500.0, 52500.0],
        "total_position_value": [50000.0, 51000.0, 50500.0, 51500.0, 52500.0],
    }
    return pd.DataFrame(data)


def test_performance_analyzer_initialization(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test PerformanceAnalyzer initialization."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)
    assert analyzer.fills_df is not None
    assert analyzer.positions_df is not None


def test_calculate_pnl_timeseries_daily(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test PnL time series calculation with daily frequency."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)
    result = analyzer.calculate_pnl_timeseries(resample_freq="1D")

    assert "pnl" in result.columns
    assert len(result) == 5  # 5 days of data
    # Check that PnL values match input
    assert result["pnl"].sum() == sample_fills_df["realized_pnl"].sum()


def test_calculate_pnl_timeseries_empty(sample_positions_df: pd.DataFrame) -> None:
    """Test PnL time series with empty fills."""
    empty_fills = pd.DataFrame(columns=["ts_fill_ns", "qty", "price", "realized_pnl"])
    analyzer = PerformanceAnalyzer(empty_fills, sample_positions_df)
    result = analyzer.calculate_pnl_timeseries()

    assert result.empty


def test_analyze_drawdowns(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test drawdown analysis."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)
    result = analyzer.analyze_drawdowns()

    assert "start" in result.columns
    assert "end" in result.columns
    assert "depth_pct" in result.columns
    assert "duration_days" in result.columns
    assert "recovery_days" in result.columns

    # Should have 1 drawdown (equity dips from 102k to 101k)
    assert len(result) >= 1
    if len(result) > 0:
        assert result["depth_pct"].iloc[0] > 0


def test_analyze_drawdowns_empty(sample_fills_df: pd.DataFrame) -> None:
    """Test drawdown analysis with empty positions."""
    empty_positions = pd.DataFrame(columns=["ts_ns", "total_equity", "cash"])
    analyzer = PerformanceAnalyzer(sample_fills_df, empty_positions)
    result = analyzer.analyze_drawdowns()

    assert result.empty


def test_analyze_trade_distribution(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test trade distribution analysis."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)
    result = analyzer.analyze_trade_distribution()

    assert "count" in result
    assert "avg_size" in result
    assert "avg_pnl" in result
    assert "pnl_percentiles" in result
    assert "win_rate" in result

    assert result["count"] == 5
    assert result["avg_size"] > 0
    assert "25%" in result["pnl_percentiles"]
    assert "50%" in result["pnl_percentiles"]
    assert "75%" in result["pnl_percentiles"]
    assert 0 <= result["win_rate"] <= 100


def test_analyze_trade_distribution_empty(sample_positions_df: pd.DataFrame) -> None:
    """Test trade distribution with empty fills."""
    empty_fills = pd.DataFrame(columns=["ts_fill_ns", "qty", "price", "realized_pnl"])
    analyzer = PerformanceAnalyzer(empty_fills, sample_positions_df)
    result = analyzer.analyze_trade_distribution()

    assert result["count"] == 0
    assert result["avg_size"] == 0.0


def test_analyze_trade_timing(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test trade timing analysis."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)
    result = analyzer.analyze_trade_timing()

    assert "hour_of_day" in result.columns
    assert "day_of_week" in result.columns
    assert "avg_pnl" in result.columns
    assert "count" in result.columns

    # All trades at midnight (hour 0)
    assert (result["hour_of_day"] == 0).all()


def test_analyze_trade_timing_empty(sample_positions_df: pd.DataFrame) -> None:
    """Test trade timing with empty fills."""
    empty_fills = pd.DataFrame(columns=["ts_fill_ns", "qty", "price", "realized_pnl"])
    analyzer = PerformanceAnalyzer(empty_fills, sample_positions_df)
    result = analyzer.analyze_trade_timing()

    assert result.empty


def test_calculate_exposure(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test exposure calculation."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)
    result = analyzer.calculate_exposure()

    assert "exposure" in result.columns
    assert len(result) == 5

    # Exposure should be between 0 and 1
    assert (result["exposure"] >= 0).all()
    assert (result["exposure"] <= 1).all()

    # With 50k position / 100k equity, should be ~0.5
    assert abs(result["exposure"].iloc[0] - 0.5) < 0.01


def test_calculate_exposure_empty(sample_fills_df: pd.DataFrame) -> None:
    """Test exposure with empty positions."""
    empty_positions = pd.DataFrame(columns=["ts_ns", "total_equity", "cash"])
    analyzer = PerformanceAnalyzer(sample_fills_df, empty_positions)
    result = analyzer.calculate_exposure()

    assert result.empty


def test_correlation_with_benchmark(
    sample_fills_df: pd.DataFrame, sample_positions_df: pd.DataFrame
) -> None:
    """Test correlation with benchmark."""
    analyzer = PerformanceAnalyzer(sample_fills_df, sample_positions_df)

    # Create benchmark returns (similar to strategy)
    benchmark_returns = pd.Series([0.02, -0.01, 0.02, 0.02, 0.01])

    result = analyzer.correlation_with_benchmark(benchmark_returns)

    assert "correlation" in result
    assert "beta" in result
    assert "alpha" in result

    # Correlation should be between -1 and 1
    assert -1 <= result["correlation"] <= 1


def test_correlation_with_benchmark_empty(sample_fills_df: pd.DataFrame) -> None:
    """Test correlation with empty positions."""
    empty_positions = pd.DataFrame(columns=["ts_ns", "total_equity", "cash"])
    analyzer = PerformanceAnalyzer(sample_fills_df, empty_positions)

    benchmark_returns = pd.Series([0.02, -0.01, 0.02])
    result = analyzer.correlation_with_benchmark(benchmark_returns)

    assert result["correlation"] == 0.0
    assert result["beta"] == 0.0
    assert result["alpha"] == 0.0
