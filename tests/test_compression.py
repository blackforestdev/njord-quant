from __future__ import annotations

import gzip
import json
import tempfile
import time
from pathlib import Path

from scripts.compress_journals import (
    compress_file,
    compress_old_journals,
    get_compression_date,
    get_file_age_hours,
)


def test_get_file_age_hours() -> None:
    """Test file age calculation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("test")

        age_hours = get_file_age_hours(test_file)

        # Should be very close to 0 (just created)
        assert age_hours < 0.1


def test_get_compression_date() -> None:
    """Test date extraction from file mtime."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("test")

        date_str = get_compression_date(test_file)

        # Should be 8-digit date: YYYYMMDD
        assert len(date_str) == 8
        assert date_str.isdigit()


def test_compress_file_basic() -> None:
    """Test basic file compression."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "ohlcv.1m.ATOMUSDT.ndjson"
        test_data = '{"symbol":"ATOM/USDT","close":10.5}\n'
        input_file.write_text(test_data)

        compressed_path = compress_file(input_file)

        # Check compressed file exists
        assert compressed_path.exists()
        assert compressed_path.suffix == ".gz"
        assert ".ndjson.gz" in compressed_path.name

        # Check original content preserved
        with gzip.open(compressed_path, "rt") as f:
            decompressed = f.read()

        assert decompressed == test_data


def test_compress_file_naming() -> None:
    """Test compressed file naming convention."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "ohlcv.5m.BTCUSDT.ndjson"
        input_file.write_text("test")

        compressed_path = compress_file(input_file)

        # Should match pattern: ohlcv.5m.BTCUSDT.YYYYMMDD.ndjson.gz
        assert "ohlcv.5m.BTCUSDT" in compressed_path.name
        assert compressed_path.name.endswith(".ndjson.gz")

        # Extract date portion (should be 8 digits)
        # compressed_path.stem removes .gz, but we still have .ndjson
        # So we need to get the name without .ndjson.gz
        name_without_gz = compressed_path.stem  # removes .gz -> ohlcv.5m.BTCUSDT.YYYYMMDD.ndjson
        name_without_ext = Path(
            name_without_gz
        ).stem  # removes .ndjson -> ohlcv.5m.BTCUSDT.YYYYMMDD
        parts = name_without_ext.split(".")
        date_part = parts[-1]  # Last part is the date
        assert len(date_part) == 8
        assert date_part.isdigit()


def test_compress_file_bit_for_bit() -> None:
    """Test compression preserves content bit-for-bit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "test.ndjson"

        # Write multi-line NDJSON
        original_lines = [
            '{"symbol":"ATOM/USDT","close":10.0}\n',
            '{"symbol":"ATOM/USDT","close":10.5}\n',
            '{"symbol":"ATOM/USDT","close":11.0}\n',
        ]
        input_file.write_text("".join(original_lines))

        compressed_path = compress_file(input_file)

        # Decompress and verify
        with gzip.open(compressed_path, "rt") as f:
            decompressed_lines = f.readlines()

        assert decompressed_lines == original_lines


def test_compress_old_journals_age_filter() -> None:
    """Test that only old files are compressed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create old file (simulate by modifying mtime)
        old_file = journal_dir / "old.ndjson"
        old_file.write_text("old")
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        old_file.touch()
        old_file.stat()  # Force refresh

        # Manually set old mtime
        import os

        os.utime(old_file, (old_time, old_time))

        # Create new file
        new_file = journal_dir / "new.ndjson"
        new_file.write_text("new")

        # Compress with 24h threshold
        stats = compress_old_journals(journal_dir, age_threshold_hours=24.0)

        # Should compress old file only
        assert stats["scanned"] == 2
        assert stats["compressed"] == 1
        assert stats["errors"] == 0

        # Old file should be compressed
        assert not old_file.exists()
        assert any(journal_dir.glob("old.*.ndjson.gz"))

        # New file should remain
        assert new_file.exists()


def test_compress_old_journals_dry_run() -> None:
    """Test dry run mode doesn't modify files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create old file
        old_file = journal_dir / "old.ndjson"
        old_file.write_text("old")

        # Set mtime to 25 hours ago
        import os

        old_time = time.time() - (25 * 3600)
        os.utime(old_file, (old_time, old_time))

        # Dry run
        stats = compress_old_journals(journal_dir, age_threshold_hours=24.0, dry_run=True)

        # Should report compression but not modify files
        assert stats["compressed"] == 1
        assert old_file.exists()
        assert not any(journal_dir.glob("*.gz"))


def test_compress_old_journals_compression_ratio() -> None:
    """Test compression ratio exceeds 50%."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create file with repetitive JSON (highly compressible)
        test_file = journal_dir / "test.ndjson"
        lines = []
        for i in range(1000):
            bar = {
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "ts_open": i * 60_000_000_000,
                "ts_close": (i + 1) * 60_000_000_000,
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.0,
                "volume": 100.0,
            }
            lines.append(json.dumps(bar) + "\n")

        test_file.write_text("".join(lines))
        original_size = test_file.stat().st_size

        # Set mtime to old
        import os

        old_time = time.time() - (25 * 3600)
        os.utime(test_file, (old_time, old_time))

        # Compress
        compress_old_journals(journal_dir, age_threshold_hours=24.0)

        # Find compressed file
        compressed_files = list(journal_dir.glob("test.*.ndjson.gz"))
        assert len(compressed_files) == 1

        compressed_size = compressed_files[0].stat().st_size
        compression_ratio = 1.0 - (compressed_size / original_size)

        # Should exceed 50% compression
        assert compression_ratio > 0.5


def test_compress_old_journals_empty_dir() -> None:
    """Test handling of empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        stats = compress_old_journals(journal_dir)

        assert stats["scanned"] == 0
        assert stats["compressed"] == 0
        assert stats["errors"] == 0


def test_compress_old_journals_nonexistent_dir() -> None:
    """Test handling of nonexistent directory."""
    nonexistent_dir = Path("/tmp/nonexistent_journal_dir_12345")

    stats = compress_old_journals(nonexistent_dir)

    assert stats["scanned"] == 0
    assert stats["compressed"] == 0
    assert stats["errors"] == 0
