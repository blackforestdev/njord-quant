"""Tests for research CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd
else:
    pd = pytest.importorskip("pandas")

from research.cli import compare_backtests, export_ohlcv, list_data, parse_timestamp, validate_data


@pytest.fixture
def mock_journal_dir(tmp_path: Path) -> Path:
    """Create mock journal directory with sample data."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    # Create OHLCV data
    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        base_ts = 1704067200000000000
        for i in range(5):
            ts = base_ts + i * 60_000_000_000
            line = {
                "ts_open": ts,
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "open": 10.0 + i,
                "high": 11.0 + i,
                "low": 9.0 + i,
                "close": 10.5 + i,
                "volume": 1000.0,
            }
            f.write(json.dumps(line) + "\n")

    return journal_dir


@pytest.fixture
def mock_backtest_results(tmp_path: Path) -> list[Path]:
    """Create mock backtest result files."""
    result_files = []

    # Strategy A
    result_a = {
        "strategy_a": {
            "strategy_id": "strategy_a",
            "symbol": "ATOM/USDT",
            "start_ts": 1704067200000000000,
            "end_ts": 1704412800000000000,
            "initial_capital": 100000.0,
            "final_capital": 115000.0,
            "total_return_pct": 15.0,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 5.0,
            "win_rate": 0.60,
            "profit_factor": 2.0,
            "num_trades": 10,
            "equity_curve": [
                {"timestamp": 1704067200000000000, "equity": 100000.0},
                {"timestamp": 1704153600000000000, "equity": 105000.0},
                {"timestamp": 1704240000000000000, "equity": 110000.0},
                {"timestamp": 1704326400000000000, "equity": 113000.0},
                {"timestamp": 1704412800000000000, "equity": 115000.0},
            ],
        }
    }

    file_a = tmp_path / "strategy_a.json"
    with file_a.open("w") as f:
        json.dump(result_a, f)
    result_files.append(file_a)

    # Strategy B
    result_b = {
        "strategy_b": {
            "strategy_id": "strategy_b",
            "symbol": "ATOM/USDT",
            "start_ts": 1704067200000000000,
            "end_ts": 1704412800000000000,
            "initial_capital": 100000.0,
            "final_capital": 108000.0,
            "total_return_pct": 8.0,
            "sharpe_ratio": 1.0,
            "max_drawdown_pct": 8.0,
            "win_rate": 0.55,
            "profit_factor": 1.8,
            "num_trades": 15,
            "equity_curve": [
                {"timestamp": 1704067200000000000, "equity": 100000.0},
                {"timestamp": 1704153600000000000, "equity": 102000.0},
                {"timestamp": 1704240000000000000, "equity": 105000.0},
                {"timestamp": 1704326400000000000, "equity": 107000.0},
                {"timestamp": 1704412800000000000, "equity": 108000.0},
            ],
        }
    }

    file_b = tmp_path / "strategy_b.json"
    with file_b.open("w") as f:
        json.dump(result_b, f)
    result_files.append(file_b)

    return result_files


def test_parse_timestamp() -> None:
    """Test timestamp parsing."""
    ts = parse_timestamp("2024-01-01")
    expected = 1704067200000000000  # 2024-01-01 00:00:00 UTC
    assert ts == expected


def test_export_ohlcv_csv(mock_journal_dir: Path, tmp_path: Path) -> None:
    """Test OHLCV export to CSV."""
    import argparse

    output_file = tmp_path / "output.csv"

    args = argparse.Namespace(
        symbol="ATOM/USDT",
        timeframe="1m",
        start="2024-01-01",
        end="2024-01-02",
        format="csv",
        compression="snappy",
        output=str(output_file),
        journal_dir=str(mock_journal_dir),
    )

    result = export_ohlcv(args)

    assert result == 0
    assert output_file.exists()

    # Verify CSV contents
    df = pd.read_csv(output_file)
    assert len(df) == 5
    assert "timestamp" in df.columns


def test_export_ohlcv_parquet(mock_journal_dir: Path, tmp_path: Path) -> None:
    """Test OHLCV export to Parquet."""
    import argparse

    output_file = tmp_path / "output.parquet"

    args = argparse.Namespace(
        symbol="ATOM/USDT",
        timeframe="1m",
        start="2024-01-01",
        end="2024-01-02",
        format="parquet",
        compression="snappy",
        output=str(output_file),
        journal_dir=str(mock_journal_dir),
    )

    result = export_ohlcv(args)

    assert result == 0
    assert output_file.exists()

    # Verify Parquet contents
    df = pd.read_parquet(output_file)
    assert len(df) == 5


def test_export_ohlcv_invalid_format(mock_journal_dir: Path, tmp_path: Path) -> None:
    """Test OHLCV export with invalid format."""
    import argparse

    output_file = tmp_path / "output.txt"

    args = argparse.Namespace(
        symbol="ATOM/USDT",
        timeframe="1m",
        start="2024-01-01",
        end="2024-01-02",
        format="invalid",
        compression="snappy",
        output=str(output_file),
        journal_dir=str(mock_journal_dir),
    )

    result = export_ohlcv(args)

    assert result == 1
    assert not output_file.exists()


def test_validate_data(
    mock_journal_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test data validation."""
    import argparse

    args = argparse.Namespace(
        symbol="ATOM/USDT",
        timeframe="1m",
        start="2024-01-01",
        end="2024-01-02",
        output=None,
        journal_dir=str(mock_journal_dir),
    )

    result = validate_data(args)

    assert result == 0

    # Check output
    captured = capsys.readouterr()
    assert "Data Quality Report" in captured.out
    assert "Quality score:" in captured.out


def test_validate_data_with_output(mock_journal_dir: Path, tmp_path: Path) -> None:
    """Test data validation with JSON output."""
    import argparse

    output_file = tmp_path / "report.json"

    args = argparse.Namespace(
        symbol="ATOM/USDT",
        timeframe="1m",
        start="2024-01-01",
        end="2024-01-02",
        output=str(output_file),
        journal_dir=str(mock_journal_dir),
    )

    result = validate_data(args)

    assert result == 0
    assert output_file.exists()

    # Verify JSON contents
    with output_file.open() as f:
        report = json.load(f)

    assert "symbol" in report
    assert report["symbol"] == "ATOM/USDT"
    assert "summary" in report


def test_list_data(mock_journal_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test list data command."""
    import argparse

    args = argparse.Namespace(journal_dir=str(mock_journal_dir))

    result = list_data(args)

    assert result == 0

    # Check output
    captured = capsys.readouterr()
    assert "ATOM/USDT" in captured.out
    assert "1m" in captured.out


def test_list_data_empty_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test list data with empty directory."""
    import argparse

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    args = argparse.Namespace(journal_dir=str(empty_dir))

    result = list_data(args)

    assert result == 0

    # Check output
    captured = capsys.readouterr()
    assert "No OHLCV data found" in captured.out


def test_compare_backtests(mock_backtest_results: list[Path], tmp_path: Path) -> None:
    """Test backtest comparison."""
    import argparse

    output_file = tmp_path / "comparison.csv"

    args = argparse.Namespace(results=mock_backtest_results, output=str(output_file))

    result = compare_backtests(args)

    assert result == 0
    assert output_file.exists()

    # Verify CSV contents
    df = pd.read_csv(output_file)
    assert len(df) == 2  # Two strategies
    assert "total_return_pct" in df.columns


def test_compare_backtests_single_result(mock_backtest_results: list[Path]) -> None:
    """Test backtest comparison with single result."""
    import argparse

    args = argparse.Namespace(results=[mock_backtest_results[0]], output=None)

    result = compare_backtests(args)

    assert result == 1  # Should fail with single result


def test_compare_backtests_no_output(
    mock_backtest_results: list[Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Test backtest comparison without output file."""
    import argparse

    args = argparse.Namespace(results=mock_backtest_results, output=None)

    result = compare_backtests(args)

    assert result == 0

    # Check output
    captured = capsys.readouterr()
    assert "Strategy Comparison" in captured.out
    assert "strategy_a" in captured.out
    assert "strategy_b" in captured.out
