from __future__ import annotations

import subprocess
import sys

import pytest

from apps.replay_engine.main import build_parser, parse_speed, parse_timestamp


def test_build_parser() -> None:
    """Test parser creation."""
    parser = build_parser()

    assert parser.prog is not None
    assert parser.description is not None
    assert "OHLCV replay engine" in parser.description


def test_parser_required_args() -> None:
    """Test that required arguments are enforced."""
    parser = build_parser()

    # Missing all required args
    with pytest.raises(SystemExit):
        parser.parse_args([])

    # Missing --end
    with pytest.raises(SystemExit):
        parser.parse_args(["--symbol", "ATOM/USDT", "--start", "2025-09-01T00:00:00Z"])

    # Missing --start
    with pytest.raises(SystemExit):
        parser.parse_args(["--symbol", "ATOM/USDT", "--end", "2025-09-30T23:59:59Z"])

    # Missing --symbol
    with pytest.raises(SystemExit):
        parser.parse_args(["--start", "2025-09-01T00:00:00Z", "--end", "2025-09-30T23:59:59Z"])


def test_parser_all_args() -> None:
    """Test parsing all arguments."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "--symbol",
            "ATOM/USDT",
            "--timeframe",
            "5m",
            "--start",
            "2025-09-01T00:00:00Z",
            "--end",
            "2025-09-30T23:59:59Z",
            "--speed",
            "10x",
            "--config",
            "./config/test.yaml",
        ]
    )

    assert args.symbol == "ATOM/USDT"
    assert args.timeframe == "5m"
    assert args.start == "2025-09-01T00:00:00Z"
    assert args.end == "2025-09-30T23:59:59Z"
    assert args.speed == "10x"
    assert args.config == "./config/test.yaml"


def test_parser_default_values() -> None:
    """Test default argument values."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-09-01T00:00:00Z",
            "--end",
            "2025-09-30T23:59:59Z",
        ]
    )

    assert args.timeframe == "1m"
    assert args.speed == "1x"
    assert args.config == "./config/base.yaml"


def test_parser_help_text() -> None:
    """Test that help text is available."""
    result = subprocess.run(
        [sys.executable, "-m", "apps.replay_engine", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OHLCV replay engine" in result.stdout
    assert "--symbol" in result.stdout
    assert "--timeframe" in result.stdout
    assert "--start" in result.stdout
    assert "--end" in result.stdout
    assert "--speed" in result.stdout
    assert "Example:" in result.stdout


def test_parse_timestamp_valid() -> None:
    """Test valid timestamp parsing."""
    # UTC timestamp with Z
    ts_ns = parse_timestamp("2025-09-01T00:00:00Z")
    assert ts_ns == 1756684800_000_000_000

    # UTC timestamp with +00:00
    ts_ns = parse_timestamp("2025-09-01T00:00:00+00:00")
    assert ts_ns == 1756684800_000_000_000

    # With microseconds
    ts_ns = parse_timestamp("2025-09-01T12:30:45.123456Z")
    expected_seconds = 1756684800 + (12 * 3600) + (30 * 60) + 45
    expected_ns = expected_seconds * 1_000_000_000 + 123_456_000
    assert ts_ns == expected_ns


def test_parse_timestamp_invalid() -> None:
    """Test invalid timestamp formats."""
    # Invalid date
    with pytest.raises(ValueError, match="Invalid timestamp format"):
        parse_timestamp("2025-13-01T00:00:00Z")

    # Completely invalid
    with pytest.raises(ValueError, match="Invalid timestamp format"):
        parse_timestamp("not a timestamp")


def test_parse_speed_valid() -> None:
    """Test valid speed parsing."""
    assert parse_speed("1x") == 1.0
    assert parse_speed("10x") == 10.0
    assert parse_speed("100x") == 100.0
    assert parse_speed("max") == 0.0

    # Without 'x' suffix
    assert parse_speed("5") == 5.0
    assert parse_speed("2.5") == 2.5

    # Case insensitivity
    assert parse_speed("MAX") == 0.0
    assert parse_speed("10X") == 10.0

    # With whitespace
    assert parse_speed(" 10x ") == 10.0


def test_parse_speed_invalid() -> None:
    """Test invalid speed formats."""
    # Negative speed (wrapped in general error message)
    with pytest.raises(ValueError, match="Invalid speed format"):
        parse_speed("-10x")

    # Invalid format
    with pytest.raises(ValueError, match="Invalid speed format"):
        parse_speed("not a speed")

    # Invalid characters
    with pytest.raises(ValueError, match="Invalid speed format"):
        parse_speed("10y")


def test_cli_error_invalid_timestamp() -> None:
    """Test CLI error handling for invalid timestamp."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.replay_engine",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "invalid-timestamp",
            "--end",
            "2025-09-30T23:59:59Z",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Invalid timestamp format" in result.stderr


def test_cli_error_invalid_speed() -> None:
    """Test CLI error handling for invalid speed."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.replay_engine",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-09-01T00:00:00Z",
            "--end",
            "2025-09-30T23:59:59Z",
            "--speed",
            "invalid",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Invalid speed format" in result.stderr


def test_cli_error_start_after_end() -> None:
    """Test CLI error when start time is after end time."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.replay_engine",
            "--symbol",
            "ATOM/USDT",
            "--start",
            "2025-09-30T23:59:59Z",
            "--end",
            "2025-09-01T00:00:00Z",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Start time must be before end time" in result.stderr


def test_parse_timestamp_iso8601_formats() -> None:
    """Test various ISO 8601 timestamp formats."""
    # Basic format
    ts1 = parse_timestamp("2025-09-01T00:00:00Z")

    # With timezone offset
    ts2 = parse_timestamp("2025-09-01T00:00:00+00:00")

    # Should be identical (both UTC)
    assert ts1 == ts2

    # Different timezone (1 hour ahead)
    ts3 = parse_timestamp("2025-09-01T01:00:00+01:00")
    assert ts3 == ts1  # Should be same instant in time


def test_parse_speed_edge_cases() -> None:
    """Test edge cases for speed parsing."""
    # Zero speed (should be allowed, means paused)
    assert parse_speed("0x") == 0.0
    assert parse_speed("0") == 0.0

    # Very large speed
    assert parse_speed("1000x") == 1000.0

    # Fractional speed
    assert parse_speed("0.5x") == 0.5
    assert parse_speed("0.1x") == 0.1
