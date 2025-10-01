"""Journal reader for OHLCV data replay.

Handles reading OHLCV bars from journal files (both compressed and uncompressed).
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, Any

from core.contracts import OHLCVBar


class JournalReaderError(Exception):
    """Raised when journal reading encounters an error."""


class JournalReader:
    """Reads OHLCV bars from journal files."""

    def __init__(self, path: Path) -> None:
        """Initialize reader for a journal directory.

        Args:
            path: Directory containing journal files
        """
        self.path = path
        if not self.path.exists():
            raise JournalReaderError(f"Journal directory does not exist: {path}")

    def read_bars(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> Iterator[OHLCVBar]:
        """Read OHLCV bars from journal files within time range.

        Args:
            symbol: Trading symbol (e.g., "ATOM/USDT")
            timeframe: Timeframe (e.g., "1m", "5m")
            start: Start timestamp (epoch nanoseconds, inclusive)
            end: End timestamp (epoch nanoseconds, exclusive)

        Yields:
            OHLCVBar objects within the time range

        Raises:
            JournalReaderError: On malformed data or missing files
        """
        # Find journal files for this symbol/timeframe
        safe_symbol = symbol.replace("/", "")
        pattern = f"ohlcv.{timeframe}.{safe_symbol}*.ndjson*"

        journal_files = sorted(self.path.glob(pattern))
        if not journal_files:
            raise JournalReaderError(
                f"No journal files found for {symbol} {timeframe} in {self.path}"
            )

        # Read from all matching files
        for journal_file in journal_files:
            yield from self._read_file(journal_file, start, end)

    def _read_file(self, file_path: Path, start: int, end: int) -> Iterator[OHLCVBar]:
        """Read bars from a single journal file."""
        # Determine if file is compressed
        is_compressed = file_path.suffix == ".gz"

        try:
            opener: Callable[[Any, str], IO[str]] = gzip.open if is_compressed else open  # type: ignore[assignment]
            with opener(file_path, "rt") as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        bar_dict = json.loads(line)
                    except json.JSONDecodeError as e:
                        raise JournalReaderError(
                            f"Malformed JSON at {file_path}:{line_num}: {e}"
                        ) from e

                    # Parse into OHLCVBar
                    try:
                        bar = OHLCVBar(**bar_dict)
                    except TypeError as e:
                        raise JournalReaderError(
                            f"Invalid bar data at {file_path}:{line_num}: {e}"
                        ) from e

                    # Filter by time range
                    if bar.ts_open >= start and bar.ts_open < end:
                        yield bar

        except OSError as e:
            raise JournalReaderError(f"Error reading {file_path}: {e}") from e


def read_all_bars(journal_dir: Path, symbol: str, timeframe: str) -> list[OHLCVBar]:
    """Convenience function to read all bars for a symbol/timeframe.

    Args:
        journal_dir: Directory containing journal files
        symbol: Trading symbol
        timeframe: Timeframe

    Returns:
        List of all bars found
    """
    reader = JournalReader(journal_dir)
    # Use very wide time range to get all bars
    return list(reader.read_bars(symbol, timeframe, start=0, end=2**63 - 1))
