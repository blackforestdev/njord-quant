"""Tests for data export utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from backtest.contracts import BacktestResult
    from research.data_reader import DataReader
    from research.export import DataExporter
else:
    pd = pytest.importorskip("pandas")
    from backtest.contracts import BacktestResult
    from research.data_reader import DataReader
    from research.export import DataExporter


@pytest.fixture
def mock_data_reader(tmp_path: Path) -> DataReader:
    """Create mock DataReader with sample data."""
    # Create sample OHLCV journal
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    # Pattern is: ohlcv.{timeframe}.{safe_symbol}*.ndjson*
    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        # Write sample OHLCV data
        for i in range(5):
            ts = 1704067200000000000 + i * 60_000_000_000  # 1-minute intervals
            line = {
                "ts_open": ts,
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "open": 10.0 + i,
                "high": 11.0 + i,
                "low": 9.0 + i,
                "close": 10.5 + i,
                "volume": 1000.0 + i * 100,
            }
            f.write(json.dumps(line) + "\n")

    # Create sample fills journal
    fills_file = journal_dir / "fills.ndjson"
    with fills_file.open("w") as f:
        for i in range(3):
            ts = 1704067200000000000 + i * 60_000_000_000
            line = {
                "ts_fill_ns": ts,
                "symbol": "ATOM/USDT",
                "side": "buy" if i % 2 == 0 else "sell",
                "qty": 10.0 + i,
                "price": 10.5 + i,
                "fee": 0.1,
                "realized_pnl": 5.0 if i > 0 else 0.0,
                "meta": {"strategy_id": "test_strategy"},
            }
            f.write(json.dumps(line) + "\n")

    # Create sample positions journal
    positions_file = journal_dir / "portfolio.ndjson"
    with positions_file.open("w") as f:
        for i in range(3):
            ts = 1704067200000000000 + i * 60_000_000_000
            line = {
                "ts_ns": ts,
                "portfolio_id": "test_portfolio",
                "symbol": "ATOM/USDT",
                "qty": 10.0 + i,
                "avg_entry_price": 10.0,
                "unrealized_pnl": 5.0 + i,
                "total_equity": 100000.0 + i * 100,
            }
            f.write(json.dumps(line) + "\n")

    return DataReader(journal_dir)


@pytest.fixture
def sample_backtest_result() -> BacktestResult:
    """Create sample backtest result."""
    return BacktestResult(
        strategy_id="test_strategy",
        symbol="ATOM/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=100000.0,
        final_capital=115000.0,
        total_return_pct=15.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=5.0,
        win_rate=0.60,
        profit_factor=2.0,
        num_trades=10,
        equity_curve=[
            (1704067200000000000, 100000.0),
            (1704153600000000000, 105000.0),
            (1704240000000000000, 110000.0),
            (1704326400000000000, 113000.0),
            (1704412800000000000, 115000.0),
        ],
    )


def test_data_exporter_initialization(mock_data_reader: DataReader) -> None:
    """Test DataExporter initialization."""
    exporter = DataExporter(mock_data_reader)
    assert exporter.data_reader is not None


def test_export_ohlcv_to_csv(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test OHLCV export to CSV."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "ohlcv.csv"

    exporter.export_ohlcv_to_csv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_csv(output_file)
    assert "timestamp" in df.columns
    assert "open" in df.columns
    assert "high" in df.columns
    assert "low" in df.columns
    assert "close" in df.columns
    assert "volume" in df.columns
    assert len(df) == 5


def test_export_ohlcv_to_csv_empty(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test OHLCV export to CSV with no data."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "ohlcv_empty.csv"

    # Export with time range that has no data
    exporter.export_ohlcv_to_csv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1700000000000000000,  # Far in past
        end_ts=1700000001000000000,
        output_path=output_file,
    )

    # Verify file exists and has headers
    assert output_file.exists()
    df = pd.read_csv(output_file)
    assert len(df) == 0
    assert "timestamp" in df.columns


def test_export_ohlcv_to_parquet(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test OHLCV export to Parquet."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "ohlcv.parquet"

    exporter.export_ohlcv_to_parquet(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
        compression="snappy",
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_parquet(output_file)
    assert "timestamp" in df.columns
    assert len(df) == 5


def test_export_ohlcv_to_parquet_gzip(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test OHLCV export to Parquet with gzip compression."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "ohlcv_gzip.parquet"

    exporter.export_ohlcv_to_parquet(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
        compression="gzip",
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_parquet(output_file)
    assert len(df) == 5


def test_export_ohlcv_to_parquet_no_compression(
    mock_data_reader: DataReader, tmp_path: Path
) -> None:
    """Test OHLCV export to Parquet without compression."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "ohlcv_none.parquet"

    exporter.export_ohlcv_to_parquet(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
        compression="none",
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_parquet(output_file)
    assert len(df) == 5


def test_export_backtest_results_to_json(
    sample_backtest_result: BacktestResult, tmp_path: Path
) -> None:
    """Test backtest results export to JSON."""
    exporter = DataExporter(DataReader(tmp_path))
    output_file = tmp_path / "results.json"

    results = {"test_strategy": sample_backtest_result}
    exporter.export_backtest_results_to_json(results, output_file)

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    with output_file.open("r") as f:
        data = json.load(f)

    assert "test_strategy" in data
    assert data["test_strategy"]["strategy_id"] == "test_strategy"
    assert data["test_strategy"]["total_return_pct"] == 15.0
    assert len(data["test_strategy"]["equity_curve"]) == 5


def test_export_backtest_results_to_json_compact(
    sample_backtest_result: BacktestResult, tmp_path: Path
) -> None:
    """Test backtest results export to JSON without indentation."""
    exporter = DataExporter(DataReader(tmp_path))
    output_file = tmp_path / "results_compact.json"

    results = {"test_strategy": sample_backtest_result}
    exporter.export_backtest_results_to_json(results, output_file, indent=None)

    # Verify file exists
    assert output_file.exists()

    # Verify it's compact (no newlines in equity curve)
    with output_file.open("r") as f:
        content = f.read()
        # Compact JSON should have fewer newlines
        assert content.count("\n") < 10


def test_export_fills_to_csv(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test fills export to CSV."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "fills.csv"

    exporter.export_fills_to_csv(
        strategy_id="test_strategy",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_csv(output_file)
    assert "timestamp" in df.columns
    assert "ts_fill_ns" in df.columns
    assert "symbol" in df.columns
    assert "side" in df.columns
    assert len(df) == 3


def test_export_fills_to_csv_all_strategies(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test fills export to CSV for all strategies."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "fills_all.csv"

    exporter.export_fills_to_csv(
        strategy_id=None,
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_csv(output_file)
    assert len(df) == 3


def test_export_positions_to_csv(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test positions export to CSV."""
    exporter = DataExporter(mock_data_reader)
    output_file = tmp_path / "positions.csv"

    exporter.export_positions_to_csv(
        portfolio_id="test_portfolio",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=output_file,
    )

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_csv(output_file)
    assert "timestamp" in df.columns
    assert "portfolio_id" in df.columns
    assert "symbol" in df.columns
    assert "qty" in df.columns
    assert len(df) == 3


def test_export_equity_curve_to_json(
    sample_backtest_result: BacktestResult, tmp_path: Path
) -> None:
    """Test equity curve export to JSON."""
    exporter = DataExporter(DataReader(tmp_path))
    output_file = tmp_path / "equity.json"

    exporter.export_equity_curve_to_json(sample_backtest_result, output_file)

    # Verify file exists
    assert output_file.exists()

    # Read and verify contents
    with output_file.open("r") as f:
        data = json.load(f)

    assert data["strategy_id"] == "test_strategy"
    assert "metrics" in data
    assert data["metrics"]["total_return_pct"] == 15.0
    assert len(data["equity_curve"]) == 5


def test_export_roundtrip_csv_parquet(mock_data_reader: DataReader, tmp_path: Path) -> None:
    """Test round-trip: CSV and Parquet should have identical data."""
    exporter = DataExporter(mock_data_reader)
    csv_file = tmp_path / "ohlcv.csv"
    parquet_file = tmp_path / "ohlcv.parquet"

    # Export to both formats
    exporter.export_ohlcv_to_csv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=csv_file,
    )

    exporter.export_ohlcv_to_parquet(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
        output_path=parquet_file,
    )

    # Read both
    df_csv = pd.read_csv(csv_file)
    df_parquet = pd.read_parquet(parquet_file)

    # Compare numeric columns (timestamps may differ in format)
    import numpy as np

    assert len(df_csv) == len(df_parquet)
    # Convert to numpy arrays first
    assert np.array_equal(np.asarray(df_csv["open"]), np.asarray(df_parquet["open"]))
    assert np.array_equal(np.asarray(df_csv["high"]), np.asarray(df_parquet["high"]))
    assert np.array_equal(np.asarray(df_csv["low"]), np.asarray(df_parquet["low"]))
    assert np.array_equal(np.asarray(df_csv["close"]), np.asarray(df_parquet["close"]))
    assert np.array_equal(np.asarray(df_csv["volume"]), np.asarray(df_parquet["volume"]))
