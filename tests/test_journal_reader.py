from __future__ import annotations

import gzip
import json
import tempfile
from pathlib import Path

import pytest

from core.contracts import OHLCVBar
from core.journal_reader import JournalReader, JournalReaderError, read_all_bars


def test_journal_reader_creation() -> None:
    """Test creating a journal reader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = JournalReader(Path(tmpdir))
        assert reader.path == Path(tmpdir)


def test_journal_reader_nonexistent_dir() -> None:
    """Test reader raises error for nonexistent directory."""
    nonexistent = Path("/tmp/nonexistent_journal_dir_xyz123")
    with pytest.raises(JournalReaderError, match="does not exist"):
        JournalReader(nonexistent)


def test_read_bars_uncompressed() -> None:
    """Test reading bars from uncompressed journal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create journal file
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        bars_data = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0 + i,
                high=11.0 + i,
                low=9.0 + i,
                close=10.5 + i,
                volume=100.0,
            )
            for i in range(10)
        ]

        # Write bars to journal
        with open(journal_file, "w") as f:
            for bar in bars_data:
                f.write(json.dumps(bar.__dict__) + "\n")

        # Read back
        reader = JournalReader(journal_dir)
        read_bars = list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))

        assert len(read_bars) == 10
        for i, bar in enumerate(read_bars):
            assert bar.symbol == "ATOM/USDT"
            assert bar.timeframe == "1m"
            assert bar.ts_open == i * 60_000_000_000
            assert bar.close == 10.5 + i


def test_read_bars_compressed() -> None:
    """Test reading bars from compressed journal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create compressed journal file
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.20250930.ndjson.gz"

        bars_data = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(5)
        ]

        # Write bars to compressed journal
        with gzip.open(journal_file, "wt") as f:
            for bar in bars_data:
                f.write(json.dumps(bar.__dict__) + "\n")

        # Read back
        reader = JournalReader(journal_dir)
        read_bars = list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))

        assert len(read_bars) == 5


def test_read_bars_time_range_filter() -> None:
    """Test time range filtering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        # Create bars spanning 0-9 minutes
        bars_data = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(10)
        ]

        with open(journal_file, "w") as f:
            for bar in bars_data:
                f.write(json.dumps(bar.__dict__) + "\n")

        reader = JournalReader(journal_dir)

        # Read bars 3-6 (inclusive start, exclusive end)
        start = 3 * 60_000_000_000
        end = 7 * 60_000_000_000

        read_bars = list(reader.read_bars("ATOM/USDT", "1m", start=start, end=end))

        assert len(read_bars) == 4  # Bars 3, 4, 5, 6
        assert read_bars[0].ts_open == 3 * 60_000_000_000
        assert read_bars[3].ts_open == 6 * 60_000_000_000


def test_read_bars_nanosecond_precision() -> None:
    """Test time range filtering with nanosecond precision."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        # Create bars with exact nanosecond timestamps
        bars_data = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=1000000000 + i,  # 1 second + i nanoseconds
                ts_close=1000000000 + i + 1,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(100)
        ]

        with open(journal_file, "w") as f:
            for bar in bars_data:
                f.write(json.dumps(bar.__dict__) + "\n")

        reader = JournalReader(journal_dir)

        # Read bars from nanosecond 10 to 50
        start = 1000000010
        end = 1000000050

        read_bars = list(reader.read_bars("ATOM/USDT", "1m", start=start, end=end))

        assert len(read_bars) == 40  # Bars 10-49
        assert read_bars[0].ts_open == 1000000010
        assert read_bars[-1].ts_open == 1000000049


def test_read_bars_malformed_json() -> None:
    """Test error handling for malformed JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        # Write malformed JSON
        with open(journal_file, "w") as f:
            f.write('{"symbol": "ATOM/USDT", "timeframe": "1m"\n')  # Missing closing brace

        reader = JournalReader(journal_dir)

        with pytest.raises(JournalReaderError, match="Malformed JSON"):
            list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))


def test_read_bars_invalid_bar_data() -> None:
    """Test error handling for invalid bar data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        # Write JSON with missing required fields
        with open(journal_file, "w") as f:
            f.write('{"symbol": "ATOM/USDT"}\n')  # Missing required fields

        reader = JournalReader(journal_dir)

        with pytest.raises(JournalReaderError, match="Invalid bar data"):
            list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))


def test_read_bars_missing_files() -> None:
    """Test error when no journal files found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        reader = JournalReader(journal_dir)

        with pytest.raises(JournalReaderError, match="No journal files found"):
            list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))


def test_read_bars_multiple_files() -> None:
    """Test reading from multiple journal files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create two journal files for the same symbol/timeframe
        file1 = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"
        file2 = journal_dir / "ohlcv.1m.ATOMUSDT.20250930.ndjson.gz"

        # Write bars to first file
        bars1 = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(5)
        ]

        with open(file1, "w") as f:
            for bar in bars1:
                f.write(json.dumps(bar.__dict__) + "\n")

        # Write bars to second file (compressed)
        bars2 = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=(i + 5) * 60_000_000_000,
                ts_close=(i + 6) * 60_000_000_000,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(5)
        ]

        with gzip.open(file2, "wt") as f:
            for bar in bars2:
                f.write(json.dumps(bar.__dict__) + "\n")

        # Read all bars
        reader = JournalReader(journal_dir)
        read_bars = list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))

        # Should have bars from both files
        assert len(read_bars) == 10


def test_read_bars_empty_lines() -> None:
    """Test handling of empty lines in journal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        bar = OHLCVBar(
            symbol="ATOM/USDT",
            timeframe="1m",
            ts_open=0,
            ts_close=60_000_000_000,
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.0,
            volume=100.0,
        )

        # Write with empty lines
        with open(journal_file, "w") as f:
            f.write("\n")
            f.write(json.dumps(bar.__dict__) + "\n")
            f.write("\n")
            f.write(json.dumps(bar.__dict__) + "\n")
            f.write("\n")

        reader = JournalReader(journal_dir)
        read_bars = list(reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1))

        # Should skip empty lines
        assert len(read_bars) == 2


def test_read_bars_iterator_pattern() -> None:
    """Test that reader uses iterator pattern (lazy loading)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        # Create large number of bars
        bars_data = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(10000)
        ]

        with open(journal_file, "w") as f:
            for bar in bars_data:
                f.write(json.dumps(bar.__dict__) + "\n")

        reader = JournalReader(journal_dir)
        bars_iter = reader.read_bars("ATOM/USDT", "1m", start=0, end=2**63 - 1)

        # Iterator should be created without reading all bars
        assert hasattr(bars_iter, "__next__")

        # Read first 10 bars only
        first_10 = [next(bars_iter) for _ in range(10)]
        assert len(first_10) == 10


def test_read_all_bars_convenience() -> None:
    """Test convenience function read_all_bars."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        bars_data = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=100.0,
            )
            for i in range(5)
        ]

        with open(journal_file, "w") as f:
            for bar in bars_data:
                f.write(json.dumps(bar.__dict__) + "\n")

        # Use convenience function
        all_bars = read_all_bars(journal_dir, "ATOM/USDT", "1m")

        assert len(all_bars) == 5
        assert isinstance(all_bars, list)
