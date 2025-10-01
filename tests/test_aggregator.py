"""Tests for data aggregator."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from research.aggregator import DataAggregator
    from research.data_reader import DataReader
else:
    pd = pytest.importorskip("pandas")
    from research.aggregator import DataAggregator
    from research.data_reader import DataReader


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """Create sample OHLCV DataFrame for testing."""
    data = {
        "timestamp": pd.date_range("2025-01-01 00:00", periods=10, freq="1min"),
        "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
        "high": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        "low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5],
        "volume": [1000.0] * 10,
    }
    df = pd.DataFrame(data)
    return df.set_index("timestamp")


@pytest.fixture
def aggregator(tmp_path: object) -> DataAggregator:
    """Create DataAggregator instance."""
    reader = DataReader(tmp_path)  # type: ignore[arg-type]
    return DataAggregator(reader)


def test_aggregator_initialization(tmp_path: object) -> None:
    """Test DataAggregator initialization."""
    reader = DataReader(tmp_path)  # type: ignore[arg-type]
    aggregator = DataAggregator(reader)
    assert aggregator.reader is reader


def test_resample_ohlcv_to_5min(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test resampling 1min bars to 5min."""
    result = aggregator.resample_ohlcv(sample_ohlcv_df, "5min")

    # Should have 2 bars (0-4 min, 5-9 min)
    assert len(result) == 2

    # First bar (0-4 min)
    assert result.iloc[0]["open"] == 100.0  # First open
    assert result.iloc[0]["high"] == 105.0  # Max high
    assert result.iloc[0]["low"] == 99.0  # Min low
    assert result.iloc[0]["close"] == 104.5  # Last close
    assert result.iloc[0]["volume"] == 5000.0  # Sum volume


def test_resample_ohlcv_empty_dataframe(aggregator: DataAggregator) -> None:
    """Test resampling empty DataFrame."""
    empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    empty_df.index = pd.DatetimeIndex([])

    result = aggregator.resample_ohlcv(empty_df, "5min")
    assert result.empty


def test_resample_ohlcv_align_wall_clock(aggregator: DataAggregator) -> None:
    """Test wall-clock alignment in resampling."""
    # Create data starting at 00:02
    data = {
        "timestamp": pd.date_range("2025-01-01 00:02", periods=8, freq="1min"),
        "open": list(range(100, 108)),
        "high": list(range(101, 109)),
        "low": list(range(99, 107)),
        "close": list(range(100, 108)),
        "volume": [1000.0] * 8,
    }
    df = pd.DataFrame(data).set_index("timestamp")

    # With wall-clock alignment, should align to 00:00, 00:05, etc.
    result = aggregator.resample_ohlcv(df, "5min", align_to_wall_clock=True)

    # Should have bars starting at 00:00 and 00:05
    assert len(result) >= 1


def test_add_indicators_sma(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test adding Simple Moving Average indicator."""
    result = aggregator.add_indicators(sample_ohlcv_df, ["sma_3"])

    assert "sma_3" in result.columns
    # First 2 values should be NaN (not enough data)
    assert pd.isna(result["sma_3"].iloc[0])
    assert pd.isna(result["sma_3"].iloc[1])
    # Third value should be average of first 3 closes
    expected_sma = (100.5 + 101.5 + 102.5) / 3
    assert abs(result["sma_3"].iloc[2] - expected_sma) < 0.01


def test_add_indicators_ema(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test adding Exponential Moving Average indicator."""
    result = aggregator.add_indicators(sample_ohlcv_df, ["ema_3"])

    assert "ema_3" in result.columns
    # EMA should have values after the first period
    assert not pd.isna(result["ema_3"].iloc[-1])


def test_add_indicators_rsi(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test adding RSI indicator."""
    result = aggregator.add_indicators(sample_ohlcv_df, ["rsi_3"])

    assert "rsi_3" in result.columns
    # RSI should be between 0 and 100
    rsi_values = result["rsi_3"].dropna()
    assert all(0 <= val <= 100 for val in rsi_values)


def test_add_indicators_macd(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test adding MACD indicator."""
    result = aggregator.add_indicators(sample_ohlcv_df, ["macd"])

    assert "macd" in result.columns
    assert "macd_signal" in result.columns
    assert "macd_histogram" in result.columns

    # Histogram should be macd - signal
    non_nan_indices = result["macd"].notna() & result["macd_signal"].notna()
    if non_nan_indices.any():
        idx = non_nan_indices.idxmax()
        macd_val = cast(float, result.loc[idx, "macd"])
        signal_val = cast(float, result.loc[idx, "macd_signal"])
        hist_val = cast(float, result.loc[idx, "macd_histogram"])
        expected_hist = macd_val - signal_val
        assert abs(hist_val - expected_hist) < 0.01


def test_add_indicators_bbands(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test adding Bollinger Bands indicator."""
    result = aggregator.add_indicators(sample_ohlcv_df, ["bbands_3_2"])

    assert "bbands_upper_3_2.0" in result.columns
    assert "bbands_middle_3_2.0" in result.columns
    assert "bbands_lower_3_2.0" in result.columns

    # Upper should be >= middle >= lower
    non_nan = result["bbands_middle_3_2.0"].notna()
    if non_nan.any():
        idx = non_nan.idxmax()
        upper = cast(float, result.loc[idx, "bbands_upper_3_2.0"])
        middle = cast(float, result.loc[idx, "bbands_middle_3_2.0"])
        lower = cast(float, result.loc[idx, "bbands_lower_3_2.0"])
        assert upper >= middle >= lower


def test_add_indicators_multiple(aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame) -> None:
    """Test adding multiple indicators at once."""
    result = aggregator.add_indicators(sample_ohlcv_df, ["sma_3", "ema_5", "rsi_5"])

    assert "sma_3" in result.columns
    assert "ema_5" in result.columns
    assert "rsi_5" in result.columns


def test_add_indicators_empty_dataframe(aggregator: DataAggregator) -> None:
    """Test adding indicators to empty DataFrame."""
    empty_df = pd.DataFrame(columns=["close"])
    empty_df.index = pd.DatetimeIndex([])

    result = aggregator.add_indicators(empty_df, ["sma_3"])
    assert result.empty


def test_add_indicators_unsupported(
    aggregator: DataAggregator, sample_ohlcv_df: pd.DataFrame
) -> None:
    """Test that unsupported indicator raises error."""
    with pytest.raises(ValueError, match="Unsupported indicator"):
        aggregator.add_indicators(sample_ohlcv_df, ["unknown_indicator"])


def test_merge_symbols_outer_join(aggregator: DataAggregator) -> None:
    """Test merging multiple symbols with outer join."""
    df1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="1D"),
            "close": [100.0, 101.0, 102.0],
        }
    ).set_index("timestamp")

    df2 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="1D"),
            "close": [200.0, 201.0, 202.0],
        }
    ).set_index("timestamp")

    result = aggregator.merge_symbols({"ATOM": df1, "ETH": df2}, how="outer")

    # Should have multi-level columns
    assert result.columns.nlevels == 2
    assert "ATOM" in result.columns.get_level_values(0)
    assert "ETH" in result.columns.get_level_values(0)

    # Should have 3 rows (all timestamps present)
    assert len(result) == 3


def test_merge_symbols_inner_join(aggregator: DataAggregator) -> None:
    """Test merging symbols with inner join."""
    df1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="1D"),
            "close": [100.0, 101.0, 102.0],
        }
    ).set_index("timestamp")

    df2 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-02", periods=2, freq="1D"),
            "close": [200.0, 201.0],
        }
    ).set_index("timestamp")

    result = aggregator.merge_symbols({"ATOM": df1, "ETH": df2}, how="inner")

    # Should only have overlapping timestamps (2 rows)
    assert len(result) == 2


def test_merge_symbols_ffill(aggregator: DataAggregator) -> None:
    """Test forward-fill in symbol merging."""
    df1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="1D"),
            "close": [100.0, 101.0, 102.0],
        }
    ).set_index("timestamp")

    df2 = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-03")],
            "close": [200.0, 202.0],
        }
    ).set_index("timestamp")

    result = aggregator.merge_symbols({"ATOM": df1, "ETH": df2}, how="outer", fill_method="ffill")

    # ETH value at 2025-01-02 should be forward-filled from 2025-01-01
    assert result.loc[pd.Timestamp("2025-01-02"), ("ETH", "close")] == 200.0


def test_merge_symbols_no_fill(aggregator: DataAggregator) -> None:
    """Test merging without forward-fill."""
    df1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="1D"),
            "close": [100.0, 101.0, 102.0],
        }
    ).set_index("timestamp")

    df2 = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-03")],
            "close": [200.0, 202.0],
        }
    ).set_index("timestamp")

    result = aggregator.merge_symbols({"ATOM": df1, "ETH": df2}, how="outer", fill_method="none")

    # ETH value at 2025-01-02 should be NaN
    assert pd.isna(result.loc[pd.Timestamp("2025-01-02"), ("ETH", "close")])


def test_merge_symbols_empty_dict(aggregator: DataAggregator) -> None:
    """Test merging with empty dictionary."""
    result = aggregator.merge_symbols({})
    assert result.empty
