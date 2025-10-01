"""Tests for backtest runner CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtest.runner import (
    format_currency,
    format_percentage,
    main,
    parse_args,
    parse_date,
    save_equity_curve,
)

# Argument parsing tests


def test_parse_args_required() -> None:
    """Test parsing required arguments."""
    args = parse_args(
        [
            "--strategy",
            "test_strategy",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-01-01",
            "--end",
            "2025-12-31",
        ]
    )

    assert args.strategy == "test_strategy"
    assert args.symbol == "ATOM/USDT"
    assert args.start == "2025-01-01"
    assert args.end == "2025-12-31"


def test_parse_args_defaults() -> None:
    """Test default argument values."""
    args = parse_args(
        [
            "--strategy",
            "test_strategy",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-01-01",
            "--end",
            "2025-12-31",
        ]
    )

    assert args.capital == 10000.0
    assert args.commission == 0.001
    assert args.slippage == 5.0
    assert args.journal_dir == Path("var/log/njord")
    assert args.output_dir == Path("var/backtest")


def test_parse_args_custom_values() -> None:
    """Test parsing custom argument values."""
    args = parse_args(
        [
            "--strategy",
            "test_strategy",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-01-01",
            "--end",
            "2025-12-31",
            "--capital",
            "50000",
            "--commission",
            "0.002",
            "--slippage",
            "10",
        ]
    )

    assert args.capital == 50000.0
    assert args.commission == 0.002
    assert args.slippage == 10.0


def test_parse_args_missing_required() -> None:
    """Test that missing required arguments raise error."""
    with pytest.raises(SystemExit):
        parse_args(["--strategy", "test_strategy"])


# Date parsing tests


def test_parse_date_valid() -> None:
    """Test parsing valid date."""
    ts_ns = parse_date("2025-01-01")

    # 2025-01-01 00:00:00 in local timezone
    # Just verify it's a reasonable timestamp (2025 range)
    # Should be around 1735689600 * 1e9 (varies by timezone)
    assert ts_ns > 1735000000 * 1_000_000_000
    assert ts_ns < 1750000000 * 1_000_000_000


def test_parse_date_invalid_format() -> None:
    """Test parsing invalid date format."""
    with pytest.raises(ValueError, match="Invalid date format"):
        parse_date("01-01-2025")


def test_parse_date_invalid_date() -> None:
    """Test parsing invalid date."""
    with pytest.raises(ValueError, match="Invalid date format"):
        parse_date("2025-13-01")  # Invalid month


# Formatting tests


def test_format_currency() -> None:
    """Test currency formatting."""
    assert format_currency(10000.0) == "$10,000.00"
    assert format_currency(12450.32) == "$12,450.32"
    assert format_currency(100.5) == "$100.50"


def test_format_percentage() -> None:
    """Test percentage formatting."""
    assert format_percentage(24.5) == "+24.50%"
    assert format_percentage(-8.23) == "-8.23%"
    assert format_percentage(0.0) == "+0.00%"


# Equity curve saving tests


def test_save_equity_curve(tmp_path: Path) -> None:
    """Test saving equity curve to file."""
    equity_curve = [
        (1000000000, 10000.0),
        (2000000000, 10500.0),
        (3000000000, 11000.0),
    ]

    output_path = save_equity_curve(
        output_dir=tmp_path,
        strategy_id="test_strategy",
        symbol="ATOM/USDT",
        equity_curve=equity_curve,
    )

    # Verify file exists
    assert output_path.exists()
    assert output_path.name == "equity_test_strategy_ATOMUSDT.ndjson"

    # Verify content
    lines = output_path.read_text().strip().split("\n")
    assert len(lines) == 3

    # Parse first line
    data = json.loads(lines[0])
    assert data["ts_ns"] == 1000000000
    assert data["equity"] == 10000.0


def test_save_equity_curve_creates_directory(tmp_path: Path) -> None:
    """Test that save_equity_curve creates output directory."""
    output_dir = tmp_path / "nested" / "dir"
    assert not output_dir.exists()

    save_equity_curve(
        output_dir=output_dir,
        strategy_id="test",
        symbol="BTC/USDT",
        equity_curve=[(1, 1000.0)],
    )

    assert output_dir.exists()


# Integration tests


def test_main_invalid_date_order(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main with invalid date order."""
    exit_code = main(
        [
            "--strategy",
            "dummy_strategy",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-12-31",
            "--end",
            "2025-01-01",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Start date must be before end date" in captured.err


def test_main_strategy_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main with non-existent strategy."""
    exit_code = main(
        [
            "--strategy",
            "nonexistent_strategy",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-01-01",
            "--end",
            "2025-01-02",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Strategy 'nonexistent_strategy' not found" in captured.err


def test_main_invalid_date_format(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main with invalid date format."""
    exit_code = main(
        [
            "--strategy",
            "dummy_strategy",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "01/01/2025",
            "--end",
            "2025-12-31",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err
