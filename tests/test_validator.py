"""Tests for data validation tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from research.data_reader import DataReader
    from research.validator import DataValidator
else:
    pd = pytest.importorskip("pandas")
    from research.data_reader import DataReader
    from research.validator import DataValidator


@pytest.fixture
def mock_data_reader_with_gaps(tmp_path: Path) -> DataReader:
    """Create mock DataReader with gaps in time series."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    # Create OHLCV data with gaps
    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        base_ts = 1704067200000000000
        for i in [0, 1, 2, 5, 6, 10]:  # Gaps at 3-4 and 7-9
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

    return DataReader(journal_dir)


@pytest.fixture
def mock_data_reader_with_anomalies(tmp_path: Path) -> DataReader:
    """Create mock DataReader with price anomalies."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        base_ts = 1704067200000000000
        for i in range(15):
            ts = base_ts + i * 60_000_000_000
            # Create spike at index 5 (20% jump)
            if i == 5:
                price = 12.0
            # Create flatline from 8-12
            elif 8 <= i <= 12:
                price = 10.0
            else:
                price = 10.0 + i * 0.1

            line = {
                "ts_open": ts,
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 1000.0,
            }
            f.write(json.dumps(line) + "\n")

    return DataReader(journal_dir)


@pytest.fixture
def mock_data_reader_with_inconsistencies(tmp_path: Path) -> DataReader:
    """Create mock DataReader with OHLCV inconsistencies."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        base_ts = 1704067200000000000

        # Bar 0: Normal
        f.write(
            json.dumps(
                {
                    "ts_open": base_ts,
                    "symbol": "ATOM/USDT",
                    "timeframe": "1m",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "volume": 1000.0,
                }
            )
            + "\n"
        )

        # Bar 1: high < low
        f.write(
            json.dumps(
                {
                    "ts_open": base_ts + 60_000_000_000,
                    "symbol": "ATOM/USDT",
                    "timeframe": "1m",
                    "open": 10.0,
                    "high": 9.0,  # Invalid: high < low
                    "low": 11.0,
                    "close": 10.5,
                    "volume": 1000.0,
                }
            )
            + "\n"
        )

        # Bar 2: close > high
        f.write(
            json.dumps(
                {
                    "ts_open": base_ts + 120_000_000_000,
                    "symbol": "ATOM/USDT",
                    "timeframe": "1m",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 12.0,  # Invalid: close > high
                    "volume": 1000.0,
                }
            )
            + "\n"
        )

    return DataReader(journal_dir)


def test_data_validator_initialization(mock_data_reader_with_gaps: DataReader) -> None:
    """Test DataValidator initialization."""
    validator = DataValidator(mock_data_reader_with_gaps)
    assert validator.reader is not None


def test_check_gaps(mock_data_reader_with_gaps: DataReader) -> None:
    """Test gap detection in time series."""
    validator = DataValidator(mock_data_reader_with_gaps)
    gaps = validator.check_gaps(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067900000000000,  # Extended to include index 10
    )

    # Should detect 2 gaps: indices 3-4 and 7-9
    assert len(gaps) == 2

    # First gap: after index 2, before index 5
    gap_start_1, gap_end_1 = gaps[0]
    assert gap_start_1 == 1704067200000000000 + 3 * 60_000_000_000
    assert gap_end_1 == 1704067200000000000 + 5 * 60_000_000_000

    # Second gap: after index 6, before index 10
    gap_start_2, gap_end_2 = gaps[1]
    assert gap_start_2 == 1704067200000000000 + 7 * 60_000_000_000
    assert gap_end_2 == 1704067200000000000 + 10 * 60_000_000_000


def test_check_gaps_no_gaps(tmp_path: Path) -> None:
    """Test gap detection with continuous data."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        base_ts = 1704067200000000000
        for i in range(5):
            ts = base_ts + i * 60_000_000_000
            line = {
                "ts_open": ts,
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1000.0,
            }
            f.write(json.dumps(line) + "\n")

    reader = DataReader(journal_dir)
    validator = DataValidator(reader)
    gaps = validator.check_gaps(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067500000000000,
    )

    assert gaps == []


def test_check_price_anomalies_spikes(mock_data_reader_with_anomalies: DataReader) -> None:
    """Test spike detection."""
    validator = DataValidator(mock_data_reader_with_anomalies)
    df = validator.reader.read_ohlcv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067900000000000,
    )

    anomalies = validator.check_price_anomalies(df, spike_threshold=0.15)

    # Should detect spike at index 5
    assert len(anomalies["spikes"]) >= 1


def test_check_price_anomalies_flatlines(mock_data_reader_with_anomalies: DataReader) -> None:
    """Test flatline detection."""
    validator = DataValidator(mock_data_reader_with_anomalies)
    df = validator.reader.read_ohlcv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067900000000000,
    )

    anomalies = validator.check_price_anomalies(df, flatline_periods=4)

    # Should detect flatline from indices 8-12 (5 consecutive)
    assert len(anomalies["flatlines"]) >= 1


def test_validate_ohlcv_consistency(mock_data_reader_with_inconsistencies: DataReader) -> None:
    """Test OHLCV consistency validation."""
    validator = DataValidator(mock_data_reader_with_inconsistencies)
    df = validator.reader.read_ohlcv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067300000000000,
    )

    issues = validator.validate_ohlcv_consistency(df)

    # Should detect issues in bars 1 and 2
    assert len(issues) >= 2

    # Check that issues contain expected fields
    assert all("ts" in issue for issue in issues)
    assert all("issue" in issue for issue in issues)


def test_validate_ohlcv_consistency_valid_data(tmp_path: Path) -> None:
    """Test OHLCV consistency with valid data."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    ohlcv_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
    with ohlcv_file.open("w") as f:
        base_ts = 1704067200000000000
        for i in range(3):
            ts = base_ts + i * 60_000_000_000
            line = {
                "ts_open": ts,
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1000.0,
            }
            f.write(json.dumps(line) + "\n")

    reader = DataReader(journal_dir)
    validator = DataValidator(reader)
    df = reader.read_ohlcv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067300000000000,
    )

    issues = validator.validate_ohlcv_consistency(df)

    assert issues == []


def test_check_fill_anomalies(tmp_path: Path) -> None:
    """Test fill anomaly detection."""
    # Create fills DataFrame
    fills_data = {
        "ts_fill_ns": [1704067200000000000, 1704067260000000000],
        "price": [10.0, 15.0],  # Second fill is 50% above market
    }
    fills_df = pd.DataFrame(fills_data)

    # Create market prices DataFrame
    market_data = {
        "ts_open": [1704067200000000000, 1704067260000000000],
        "close": [10.0, 10.5],  # Market price at 10.5
    }
    market_df = pd.DataFrame(market_data)

    validator = DataValidator(DataReader(tmp_path))
    anomalies = validator.check_fill_anomalies(fills_df, market_df, deviation_threshold=0.02)

    # Should detect anomaly for second fill (15.0 vs 10.5 market)
    assert len(anomalies) == 1
    assert anomalies[0]["fill_price"] == 15.0
    assert anomalies[0]["deviation_pct"] > 40.0


def test_generate_quality_report(mock_data_reader_with_gaps: DataReader) -> None:
    """Test quality report generation."""
    validator = DataValidator(mock_data_reader_with_gaps)
    report = validator.generate_quality_report(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=1704067200000000000,
        end_ts=1704067900000000000,  # Extended to include index 10
    )

    assert "symbol" in report
    assert report["symbol"] == "ATOM/USDT"
    assert "timeframe" in report
    assert report["timeframe"] == "1m"
    assert "total_bars" in report
    assert report["total_bars"] == 6
    assert "gaps" in report
    assert "price_anomalies" in report
    assert "consistency_issues" in report
    assert "summary" in report
    assert "quality_score" in report["summary"]


def test_parse_timeframe_to_ns(tmp_path: Path) -> None:
    """Test timeframe parsing."""
    validator = DataValidator(DataReader(tmp_path))

    assert validator._parse_timeframe_to_ns("1m") == 60_000_000_000
    assert validator._parse_timeframe_to_ns("5m") == 300_000_000_000
    assert validator._parse_timeframe_to_ns("1h") == 3_600_000_000_000
    assert validator._parse_timeframe_to_ns("1d") == 86_400_000_000_000


def test_parse_timeframe_to_ns_invalid(tmp_path: Path) -> None:
    """Test timeframe parsing with invalid format."""
    validator = DataValidator(DataReader(tmp_path))

    with pytest.raises(ValueError, match="Invalid timeframe format"):
        validator._parse_timeframe_to_ns("invalid")


def test_calculate_quality_score(tmp_path: Path) -> None:
    """Test quality score calculation."""
    validator = DataValidator(DataReader(tmp_path))

    # Perfect data
    report_perfect = {
        "total_bars": 100,
        "summary": {
            "total_gaps": 0,
            "total_spikes": 0,
            "total_flatlines": 0,
            "total_consistency_issues": 0,
        },
    }
    score = validator._calculate_quality_score(report_perfect)
    assert score == 100.0

    # Data with issues
    report_issues = {
        "total_bars": 100,
        "summary": {
            "total_gaps": 5,
            "total_spikes": 10,
            "total_flatlines": 20,
            "total_consistency_issues": 2,
        },
    }
    score = validator._calculate_quality_score(report_issues)
    assert score < 100.0
    assert score >= 0.0
