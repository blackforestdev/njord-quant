#!/usr/bin/env python3
"""Compress old OHLCV journal files with gzip.

This script scans for .ndjson files in the journal directory,
compresses files older than 24 hours, and removes the originals.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path


def get_file_age_hours(file_path: Path) -> float:
    """Return age of file in hours."""
    mtime = file_path.stat().st_mtime
    age_seconds = time.time() - mtime
    return age_seconds / 3600.0


def get_compression_date(file_path: Path) -> str:
    """Get YYYYMMDD from file modification time."""
    mtime = file_path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=UTC)
    return dt.strftime("%Y%m%d")


def compress_file(input_path: Path, compression_level: int = 6) -> Path:
    """Compress file with gzip and return compressed path.

    Renames: file.ndjson → file.YYYYMMDD.ndjson.gz
    """
    date_str = get_compression_date(input_path)

    # Build output path
    # Example: ohlcv.1m.ATOMUSDT.ndjson → ohlcv.1m.ATOMUSDT.20250930.ndjson.gz
    stem = input_path.stem  # ohlcv.1m.ATOMUSDT
    output_path = input_path.parent / f"{stem}.{date_str}.ndjson.gz"

    # Compress
    with (
        open(input_path, "rb") as f_in,
        gzip.open(output_path, "wb", compresslevel=compression_level) as f_out,
    ):
        shutil.copyfileobj(f_in, f_out)

    return output_path


def compress_old_journals(
    journal_dir: Path,
    age_threshold_hours: float = 24.0,
    compression_level: int = 6,
    dry_run: bool = False,
) -> dict[str, int]:
    """Compress NDJSON journals older than threshold.

    Returns dict with counts: {scanned, compressed, errors}
    """
    stats = {"scanned": 0, "compressed": 0, "errors": 0}

    if not journal_dir.exists():
        return stats

    # Find all .ndjson files
    for ndjson_file in journal_dir.glob("*.ndjson"):
        stats["scanned"] += 1

        try:
            age_hours = get_file_age_hours(ndjson_file)

            if age_hours < age_threshold_hours:
                continue

            if dry_run:
                print(f"[DRY RUN] Would compress: {ndjson_file}")
                stats["compressed"] += 1
                continue

            # Compress
            compressed_path = compress_file(ndjson_file, compression_level)

            # Remove original
            ndjson_file.unlink()

            stats["compressed"] += 1
            print(f"Compressed: {ndjson_file} → {compressed_path.name}")

        except Exception as e:
            stats["errors"] += 1
            print(f"Error compressing {ndjson_file}: {e}")

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compress old OHLCV journals")
    parser.add_argument(
        "--journal-dir",
        type=Path,
        default=Path("var/log/njord"),
        help="Journal directory (default: var/log/njord)",
    )
    parser.add_argument(
        "--age-hours",
        type=float,
        default=24.0,
        help="Compress files older than this many hours (default: 24)",
    )
    parser.add_argument(
        "--compression-level",
        type=int,
        default=6,
        help="Gzip compression level 1-9 (default: 6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be compressed without doing it",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    stats = compress_old_journals(
        journal_dir=args.journal_dir,
        age_threshold_hours=args.age_hours,
        compression_level=args.compression_level,
        dry_run=args.dry_run,
    )

    print(
        f"\nSummary: scanned={stats['scanned']}, "
        f"compressed={stats['compressed']}, errors={stats['errors']}"
    )


if __name__ == "__main__":
    main()
