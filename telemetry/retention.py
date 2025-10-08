"""Metrics retention and cleanup for managing journal disk usage.

This module implements retention policies for metrics journals, including
downsampling, compression, and deletion of old data.
"""

from __future__ import annotations

import gzip
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from telemetry.contracts import RetentionPolicy

logger = logging.getLogger(__name__)

# Resolution to seconds mapping
_RESOLUTION_SECONDS = {
    "1m": 60,
    "5m": 300,
    "1h": 3600,
    "1d": 86400,
}


class MetricsRetention:
    """Metrics retention manager.

    Manages retention policies for metrics journals, including downsampling,
    compression, and deletion of old data.

    Attributes:
        journal_dir: Directory containing metrics journals
        policy: Retention policy configuration
    """

    def __init__(self, journal_dir: Path, policy: RetentionPolicy) -> None:
        """Initialize metrics retention manager.

        Args:
            journal_dir: Directory containing metrics journals
            policy: Retention policy configuration
        """
        self.journal_dir = journal_dir
        self.policy = policy

        if not self.journal_dir.exists():
            self.journal_dir.mkdir(parents=True, exist_ok=True)

    def apply_retention(self) -> dict[str, int]:
        """Apply retention policy to metrics journals.

        Returns:
            Dict with operation counts (downsampled, compressed, deleted)
        """
        stats = {
            "downsampled": 0,
            "compressed": 0,
            "deleted": 0,
        }

        logger.info("retention.apply_start", extra={"journal_dir": str(self.journal_dir)})

        # Sort retention levels by retention_days (shortest first)
        sorted_levels = sorted(self.policy.raw_metrics, key=lambda x: x.retention_days)

        # Apply retention for each level
        for i, level in enumerate(sorted_levels):
            # Delete metrics older than this level's retention
            deleted = self.delete_expired(level.retention_days)
            stats["deleted"] += deleted

            # Downsample to next level if available
            if i + 1 < len(sorted_levels):
                next_level = sorted_levels[i + 1]
                downsampled = self.downsample_metrics(
                    source_resolution=level.resolution,
                    target_resolution=next_level.resolution,
                    cutoff_days=level.retention_days,
                )
                stats["downsampled"] += downsampled

        # Compress old journals (older than 7 days)
        compressed = self.compress_journals(older_than_days=7)
        stats["compressed"] += compressed

        logger.info(
            "retention.apply_complete",
            extra={
                "journal_dir": str(self.journal_dir),
                "downsampled": stats["downsampled"],
                "compressed": stats["compressed"],
                "deleted": stats["deleted"],
            },
        )

        return stats

    def downsample_metrics(
        self, source_resolution: str, target_resolution: str, cutoff_days: int
    ) -> int:
        """Downsample metrics older than cutoff.

        Args:
            source_resolution: Source resolution (e.g., "1m")
            target_resolution: Target resolution (e.g., "5m")
            cutoff_days: Downsample metrics older than this many days

        Returns:
            Number of files downsampled
        """
        if source_resolution not in _RESOLUTION_SECONDS:
            logger.warning(
                "retention.unknown_resolution",
                extra={"resolution": source_resolution},
            )
            return 0

        if target_resolution not in _RESOLUTION_SECONDS:
            logger.warning(
                "retention.unknown_resolution",
                extra={"resolution": target_resolution},
            )
            return 0

        cutoff_time_ns = int((time.time() - cutoff_days * 86400) * 1_000_000_000)
        downsampled_count = 0

        # Find journal files to downsample
        pattern = f"*_{source_resolution}.jsonl"
        for journal_file in self.journal_dir.glob(pattern):
            # Check if file is old enough
            if journal_file.stat().st_mtime_ns > cutoff_time_ns:
                continue

            # Downsample this file
            target_file = journal_file.with_name(
                journal_file.name.replace(f"_{source_resolution}", f"_{target_resolution}")
            )

            if self._downsample_file(journal_file, target_file, target_resolution):
                downsampled_count += 1
                logger.debug(
                    "retention.downsampled",
                    extra={
                        "source": str(journal_file),
                        "target": str(target_file),
                        "resolution": target_resolution,
                    },
                )

        return downsampled_count

    def _downsample_file(
        self, source_file: Path, target_file: Path, target_resolution: str
    ) -> bool:
        """Downsample a single journal file.

        Args:
            source_file: Source journal file
            target_file: Target journal file
            target_resolution: Target resolution

        Returns:
            True if downsampled successfully
        """
        try:
            # Read source metrics
            metrics: list[dict[str, Any]] = []
            with source_file.open() as f:
                for line in f:
                    if line.strip():
                        metrics.append(json.loads(line))

            if not metrics:
                return False

            # Group metrics by time bucket
            bucket_size_ns = _RESOLUTION_SECONDS[target_resolution] * 1_000_000_000
            buckets: dict[int, list[dict[str, Any]]] = {}

            for metric in metrics:
                timestamp_ns = metric.get("timestamp_ns", 0)
                bucket_key = timestamp_ns // bucket_size_ns
                if bucket_key not in buckets:
                    buckets[bucket_key] = []
                buckets[bucket_key].append(metric)

            # Aggregate each bucket
            aggregated: list[dict[str, Any]] = []
            for bucket_key, bucket_metrics in sorted(buckets.items()):
                if not bucket_metrics:
                    continue

                # Use first metric as template
                agg_metric = bucket_metrics[0].copy()

                # Average the values
                if len(bucket_metrics) > 1:
                    total_value = sum(m.get("value", 0.0) for m in bucket_metrics)
                    agg_metric["value"] = total_value / len(bucket_metrics)

                # Set timestamp to bucket start
                agg_metric["timestamp_ns"] = bucket_key * bucket_size_ns

                aggregated.append(agg_metric)

            # Write to target file
            with target_file.open("w") as f:
                for metric in aggregated:
                    f.write(json.dumps(metric) + "\n")

            return True

        except Exception as e:
            logger.error(
                "retention.downsample_error",
                extra={
                    "source": str(source_file),
                    "target": str(target_file),
                    "error": str(e),
                },
            )
            return False

    def compress_journals(self, older_than_days: int) -> int:
        """Compress journals older than threshold.

        Args:
            older_than_days: Compress journals older than this many days

        Returns:
            Number of files compressed
        """
        cutoff_time_ns = int((time.time() - older_than_days * 86400) * 1_000_000_000)
        compressed_count = 0

        # Find uncompressed journal files
        for journal_file in self.journal_dir.glob("*.jsonl"):
            # Skip if already compressed
            if journal_file.suffix == ".gz":
                continue

            # Check if file is old enough
            if journal_file.stat().st_mtime_ns > cutoff_time_ns:
                continue

            # Compress this file
            compressed_file = journal_file.with_suffix(".jsonl.gz")

            if self._compress_file(journal_file, compressed_file):
                compressed_count += 1
                logger.debug(
                    "retention.compressed",
                    extra={
                        "source": str(journal_file),
                        "target": str(compressed_file),
                    },
                )

        return compressed_count

    def _compress_file(self, source_file: Path, target_file: Path) -> bool:
        """Compress a single journal file.

        Args:
            source_file: Source journal file
            target_file: Target compressed file

        Returns:
            True if compressed successfully
        """
        try:
            with source_file.open("rb") as f_in, gzip.open(target_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # Delete original file after successful compression
            source_file.unlink()
            return True

        except Exception as e:
            logger.error(
                "retention.compress_error",
                extra={
                    "source": str(source_file),
                    "target": str(target_file),
                    "error": str(e),
                },
            )
            return False

    def delete_expired(self, older_than_days: int) -> int:
        """Delete metrics older than retention period.

        Args:
            older_than_days: Delete metrics older than this many days

        Returns:
            Number of files deleted
        """
        cutoff_time_ns = int((time.time() - older_than_days * 86400) * 1_000_000_000)
        deleted_count = 0

        # Find expired journal files
        for journal_file in self.journal_dir.glob("*.jsonl*"):
            # Check if file is old enough
            if journal_file.stat().st_mtime_ns >= cutoff_time_ns:
                continue

            # Delete this file
            try:
                journal_file.unlink()
                deleted_count += 1
                logger.debug(
                    "retention.deleted",
                    extra={"file": str(journal_file)},
                )
            except Exception as e:
                logger.error(
                    "retention.delete_error",
                    extra={"file": str(journal_file), "error": str(e)},
                )

        return deleted_count


def validate_cron_schedule(schedule: str) -> bool:
    """Validate cron schedule format.

    Args:
        schedule: Cron schedule string (e.g., "0 2 * * *")

    Returns:
        True if valid, False otherwise
    """
    parts = schedule.split()
    if len(parts) != 5:
        return False

    # Basic validation: each part should be numeric, *, or contain numeric ranges/lists
    for part in parts:
        if part == "*":
            continue
        if part.isdigit():
            continue
        # Check for ranges (e.g., "1-5"), lists (e.g., "1,3,5"), or steps (e.g., "*/5")
        if all(c.isdigit() or c in "-,/*" for c in part):
            continue
        return False

    return True
