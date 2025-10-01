from __future__ import annotations

import gzip
import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.ohlcv_aggregator.rotator import JournalRotator


def test_rotator_creation() -> None:
    """Test creating a journal rotator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"
        journal_path.write_text("test")

        rotator = JournalRotator(journal_path)

        assert rotator.journal_path == journal_path
        assert rotator.max_size_bytes == 100 * 1024 * 1024  # 100MB


def test_should_rotate_date_change() -> None:
    """Test rotation triggers on date change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"
        journal_path.write_text("test")

        rotator = JournalRotator(journal_path)

        # Initially should not rotate (same date)
        assert not rotator.should_rotate()

        # Mock date change
        with patch.object(rotator, "_get_current_date", return_value="20250101"):
            assert rotator.should_rotate()


def test_should_rotate_size_threshold() -> None:
    """Test rotation triggers at 100MB threshold."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"

        # Create file just under 100MB
        size_99mb = 99 * 1024 * 1024
        with open(journal_path, "wb") as f:
            f.write(b"x" * size_99mb)

        rotator = JournalRotator(journal_path)
        assert not rotator.should_rotate()

        # Expand to 100MB+
        with open(journal_path, "ab") as f:
            f.write(b"x" * (2 * 1024 * 1024))  # Add 2MB

        assert rotator.should_rotate()


def test_should_rotate_nonexistent_file() -> None:
    """Test should_rotate returns False for nonexistent file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "nonexistent.ndjson"

        rotator = JournalRotator(journal_path)
        assert not rotator.should_rotate()


def test_rotate_basic() -> None:
    """Test basic rotation without compression."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "ohlcv.1m.ATOMUSDT.ndjson"
        test_content = "test content\n"
        journal_path.write_text(test_content)

        rotator = JournalRotator(journal_path)
        # Set initial date manually
        rotator.current_date = "20250930"

        rotated_path = rotator.rotate(compress=False)

        assert rotated_path is not None
        assert "20250930" in rotated_path.name
        assert rotated_path.exists()
        assert rotated_path.read_text() == test_content

        # Original should be gone
        assert not journal_path.exists()


def test_rotate_with_compression() -> None:
    """Test rotation with gzip compression."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "ohlcv.1m.ATOMUSDT.ndjson"
        test_content = "test content\n"
        journal_path.write_text(test_content)

        rotator = JournalRotator(journal_path)
        rotator.current_date = "20250930"

        rotated_path = rotator.rotate(compress=True)

        assert rotated_path is not None
        assert rotated_path.suffix == ".gz"
        assert "20250930" in rotated_path.name

        # Verify compressed content
        with gzip.open(rotated_path, "rt") as f:
            decompressed = f.read()

        assert decompressed == test_content


def test_rotate_naming_convention() -> None:
    """Test rotated file follows naming convention."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "ohlcv.5m.BTCUSDT.ndjson"
        journal_path.write_text("test")

        rotator = JournalRotator(journal_path)
        rotator.current_date = "20250930"

        rotated_path = rotator.rotate(compress=False)

        # Should be: ohlcv.5m.BTCUSDT.20250930.ndjson
        assert rotated_path is not None
        assert rotated_path.name == "ohlcv.5m.BTCUSDT.20250930.ndjson"


def test_rotate_duplicate_handling() -> None:
    """Test rotation handles duplicate filenames with counter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"

        # Create first rotation
        journal_path.write_text("first")
        rotator1 = JournalRotator(journal_path)
        rotator1.current_date = "20250930"
        first_rotated = rotator1.rotate(compress=False)

        assert first_rotated is not None
        assert first_rotated.name == "test.20250930.ndjson"

        # Create second rotation (same date)
        journal_path.write_text("second")
        rotator2 = JournalRotator(journal_path)
        rotator2.current_date = "20250930"
        second_rotated = rotator2.rotate(compress=False)

        assert second_rotated is not None
        assert second_rotated.name == "test.20250930.1.ndjson"


def test_rotate_no_data_loss() -> None:
    """Test rotation preserves all data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"

        # Write multi-line content
        lines = [f"line {i}\n" for i in range(1000)]
        journal_path.write_text("".join(lines))

        original_content = journal_path.read_text()

        rotator = JournalRotator(journal_path)
        with patch.object(rotator, "_get_current_date", return_value="20250930"):
            rotated_path = rotator.rotate(compress=True)

        # Verify no data loss
        assert rotated_path is not None
        with gzip.open(rotated_path, "rt") as f:
            rotated_content = f.read()

        assert rotated_content == original_content


def test_rotate_nonexistent_file() -> None:
    """Test rotating nonexistent file returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "nonexistent.ndjson"

        rotator = JournalRotator(journal_path)
        rotated_path = rotator.rotate()

        assert rotated_path is None


def test_rotate_updates_current_date() -> None:
    """Test rotation updates current_date tracking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"
        journal_path.write_text("test")

        rotator = JournalRotator(journal_path)
        original_date = rotator.current_date

        # Mock date change during rotation
        with patch.object(rotator, "_get_current_date", return_value="20250101"):
            rotator.rotate()

        # Current date should be updated
        assert rotator.current_date == "20250101"
        assert rotator.current_date != original_date


def test_midnight_utc_rotation_simulation() -> None:
    """Test simulated midnight UTC rotation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "ohlcv.1m.ATOMUSDT.ndjson"

        # Simulate writes on day 1
        journal_path.write_text("day1 data\n")
        rotator = JournalRotator(journal_path)

        # Set initial date
        day1 = "20250930"
        rotator.current_date = day1

        # Simulate midnight - date changes to day 2
        day2 = "20251001"

        with patch.object(rotator, "_get_current_date", return_value=day2):
            # Should trigger rotation
            assert rotator.should_rotate()

            # Perform rotation
            rotated_path = rotator.rotate(compress=False)

        # Verify rotated file has day1 date
        assert rotated_path is not None
        assert day1 in rotated_path.name

        # Write day2 data to new journal
        journal_path.write_text("day2 data\n")

        # Rotator should now track day2
        assert rotator.current_date == day2


def test_custom_size_threshold() -> None:
    """Test custom size threshold."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "test.ndjson"

        # Create 10KB file
        with open(journal_path, "wb") as f:
            f.write(b"x" * 10_000)

        # Rotator with 5KB threshold
        rotator = JournalRotator(journal_path, max_size_bytes=5_000)

        # Should trigger rotation
        assert rotator.should_rotate()
