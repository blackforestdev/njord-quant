"""Journal rotation logic for OHLCV aggregator.

Handles daily rotation (midnight UTC) and size-based rotation (100MB threshold).
"""

from __future__ import annotations

import gzip
import shutil
from datetime import UTC, datetime
from pathlib import Path


class JournalRotator:
    """Manages journal rotation by date and size."""

    def __init__(
        self,
        journal_path: Path,
        max_size_bytes: int = 100 * 1024 * 1024,  # 100MB
    ) -> None:
        self.journal_path = journal_path
        self.max_size_bytes = max_size_bytes
        self.current_date = self._get_current_date()

    def _get_current_date(self) -> str:
        """Get current date in YYYYMMDD format."""
        return datetime.now(UTC).strftime("%Y%m%d")

    def should_rotate(self) -> bool:
        """Check if rotation is needed (date change or size threshold)."""
        if not self.journal_path.exists():
            return False

        # Check date rotation
        current_date = self._get_current_date()
        if current_date != self.current_date:
            return True

        # Check size rotation
        file_size = self.journal_path.stat().st_size
        return file_size >= self.max_size_bytes

    def rotate(self, compress: bool = True) -> Path | None:
        """Rotate journal file and optionally compress.

        Returns path to rotated file, or None if nothing to rotate.
        """
        if not self.journal_path.exists():
            return None

        # Build rotated filename using current_date (not _get_current_date())
        # This ensures we use the date when the journal was active, not when rotation happens
        # Example: ohlcv.1m.ATOMUSDT.ndjson → ohlcv.1m.ATOMUSDT.20250930.ndjson
        date_str = self.current_date
        stem = self.journal_path.stem  # e.g., ohlcv.1m.ATOMUSDT
        suffix = self.journal_path.suffix  # .ndjson

        rotated_path = self.journal_path.parent / f"{stem}.{date_str}{suffix}"

        # If rotated file already exists, append counter
        counter = 1
        while rotated_path.exists():
            rotated_path = self.journal_path.parent / f"{stem}.{date_str}.{counter}{suffix}"
            counter += 1

        # Move current journal to rotated path
        shutil.move(str(self.journal_path), str(rotated_path))

        # Compress if requested
        if compress:
            compressed_path = self._compress_rotated(rotated_path)
            rotated_path.unlink()  # Remove uncompressed
            final_path = compressed_path
        else:
            final_path = rotated_path

        # Update current date
        self.current_date = self._get_current_date()

        return final_path

    def _compress_rotated(self, rotated_path: Path) -> Path:
        """Compress rotated file with gzip."""
        compressed_path = rotated_path.with_suffix(rotated_path.suffix + ".gz")

        with (
            open(rotated_path, "rb") as f_in,
            gzip.open(compressed_path, "wb", compresslevel=6) as f_out,
        ):
            shutil.copyfileobj(f_in, f_out)

        return compressed_path
