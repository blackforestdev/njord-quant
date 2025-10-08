"""Metric aggregation service for downsampling and persistence."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telemetry.contracts import MetricSnapshot

LabelsKey = tuple[tuple[str, str], ...]

if TYPE_CHECKING:
    from telemetry.registry import MetricRegistry

logger = logging.getLogger(__name__)


@dataclass
class AggregationBucket:
    """Time-based bucket for aggregating metrics.

    Attributes:
        start_ts_ns: Bucket start timestamp (nanoseconds)
        interval_seconds: Bucket duration (seconds)
        counters: Aggregated counter values {metric_name: {labels_key: sum}}
        gauges: Aggregated gauge values {metric_name: {labels_key: (sum, count)}}
        histograms: Aggregated histogram data {metric_name: {labels_key: (buckets, sum, count)}}
    """

    start_ts_ns: int
    interval_seconds: int
    counters: dict[str, dict[LabelsKey, float]] = field(default_factory=lambda: defaultdict(dict))
    gauges: dict[str, dict[LabelsKey, tuple[float, int]]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    histograms: dict[str, dict[LabelsKey, list[float]]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    @property
    def end_ts_ns(self) -> int:
        """Bucket end timestamp."""
        return self.start_ts_ns + (self.interval_seconds * 1_000_000_000)

    def contains(self, timestamp_ns: int) -> bool:
        """Check if timestamp falls within this bucket."""
        return self.start_ts_ns <= timestamp_ns < self.end_ts_ns

    def add_metric(self, snapshot: MetricSnapshot) -> None:
        """Add metric snapshot to this bucket.

        Args:
            snapshot: Metric snapshot to aggregate
        """
        # Convert labels dict to sorted tuple for use as dict key
        labels_key: LabelsKey = tuple(sorted(snapshot.labels.items()))

        if snapshot.metric_type == "counter":
            if snapshot.name not in self.counters:
                self.counters[snapshot.name] = {}
            self.counters[snapshot.name][labels_key] = (
                self.counters[snapshot.name].get(labels_key, 0.0) + snapshot.value
            )

        elif snapshot.metric_type == "gauge":
            if snapshot.name not in self.gauges:
                self.gauges[snapshot.name] = {}

            current_sum, current_count = self.gauges[snapshot.name].get(labels_key, (0.0, 0))
            self.gauges[snapshot.name][labels_key] = (
                current_sum + snapshot.value,
                current_count + 1,
            )

        elif snapshot.metric_type == "histogram":
            # For histograms, we store individual observations
            # They'll be re-bucketed when publishing to registry
            if snapshot.name not in self.histograms:
                self.histograms[snapshot.name] = {}

            if labels_key not in self.histograms[snapshot.name]:
                self.histograms[snapshot.name][labels_key] = []
            self.histograms[snapshot.name][labels_key].append(snapshot.value)


class MetricAggregator:
    """Centralized service for metric aggregation and persistence.

    Aggregates raw metrics into time-based buckets, downsamples old data,
    and publishes to shared MetricRegistry for Prometheus scraping.
    """

    def __init__(
        self,
        bus: Any,
        journal_dir: Path,
        registry: MetricRegistry,
        retention_hours: int = 168,  # 7 days
        flush_interval_seconds: int = 60,  # 1 minute
        grace_period_seconds: int = 300,  # 5 minutes
    ) -> None:
        """Initialize metric aggregator.

        Args:
            bus: Event bus for subscribing to metrics
            journal_dir: Directory for persisting aggregated metrics
            registry: Shared MetricRegistry (used by PrometheusExporter)
            retention_hours: How long to keep raw metrics
            flush_interval_seconds: How often to flush to journal and registry
            grace_period_seconds: Accept late metrics within this window
        """
        self.bus = bus
        self.journal_dir = Path(journal_dir)
        self.registry = registry
        self.retention_hours = retention_hours
        self.flush_interval_seconds = flush_interval_seconds
        self.grace_period_seconds = grace_period_seconds

        # Create journal directory
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.journal_dir / "aggregated_metrics.ndjson"
        self.journal_path.touch(exist_ok=True)

        # Time-based buckets: {bucket_start_ts_ns: AggregationBucket}
        self._buckets: dict[int, AggregationBucket] = {}
        self._lock = asyncio.Lock()

        # Track which metrics have been registered in the registry
        self._registered_metrics: set[tuple[str, str]] = set()  # {(name, type)}

    async def run(self) -> None:
        """Main aggregation loop.

        Subscribes to telemetry.metrics and processes incoming metrics.
        Periodically flushes to journal and registry.
        """
        # Start flush task
        flush_task = asyncio.create_task(self._periodic_flush())

        try:
            async for snapshot_dict in self.bus.subscribe("telemetry.metrics"):
                snapshot = MetricSnapshot.from_dict(snapshot_dict)
                await self.aggregate_metrics(snapshot)
        finally:
            flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flush_task

    async def aggregate_metrics(self, snapshot: MetricSnapshot) -> None:
        """Aggregate incoming metric snapshot.

        Args:
            snapshot: Metric snapshot to aggregate
        """
        async with self._lock:
            # Find or create appropriate bucket (1-minute interval)
            bucket = self._get_or_create_bucket(snapshot.timestamp_ns, interval_seconds=60)

            # Add metric to bucket
            bucket.add_metric(snapshot)

            # Evict old buckets beyond retention window
            await self._evict_old_buckets()

    def _get_or_create_bucket(self, timestamp_ns: int, interval_seconds: int) -> AggregationBucket:
        """Get or create aggregation bucket for timestamp.

        Args:
            timestamp_ns: Metric timestamp
            interval_seconds: Bucket interval

        Returns:
            AggregationBucket for this time window
        """
        # Round down to bucket start
        interval_ns = interval_seconds * 1_000_000_000
        bucket_start_ns = (timestamp_ns // interval_ns) * interval_ns

        if bucket_start_ns not in self._buckets:
            self._buckets[bucket_start_ns] = AggregationBucket(
                start_ts_ns=bucket_start_ns, interval_seconds=interval_seconds
            )

        return self._buckets[bucket_start_ns]

    async def _evict_old_buckets(self) -> None:
        """Evict buckets older than retention window."""
        now_ns = time.time_ns()
        retention_ns = self.retention_hours * 3600 * 1_000_000_000
        cutoff_ns = now_ns - retention_ns

        # Remove buckets older than retention + grace period
        grace_ns = self.grace_period_seconds * 1_000_000_000
        eviction_cutoff_ns = cutoff_ns - grace_ns

        evicted_count = 0
        for bucket_start_ns in list(self._buckets.keys()):
            if bucket_start_ns < eviction_cutoff_ns:
                del self._buckets[bucket_start_ns]
                evicted_count += 1

        if evicted_count > 0:
            logger.debug(
                "telemetry.aggregator_evicted_buckets",
                extra={"count": evicted_count, "cutoff_ts_ns": eviction_cutoff_ns},
            )

    async def _periodic_flush(self) -> None:
        """Periodically flush aggregated metrics to journal and registry."""
        while True:
            await asyncio.sleep(self.flush_interval_seconds)

            try:
                async with self._lock:
                    lines = await self._flush_to_registry()
                    self._flush_to_journal(lines)
            except Exception:
                logger.exception("telemetry.aggregator_flush_failed")

    async def _flush_to_registry(self) -> list[str]:
        """Publish aggregated metrics to shared MetricRegistry.

        CRITICAL: This is how PrometheusExporter accesses aggregated data.
        """
        now_ns = time.time_ns()
        grace_ns = self.grace_period_seconds * 1_000_000_000

        # Only flush buckets that are beyond the grace period
        # (so we don't flush incomplete data from late arrivals)
        flush_cutoff_ns = now_ns - grace_ns

        lines: list[str] = []
        flushed_keys: list[int] = []

        for bucket_start_ns, bucket in self._buckets.items():
            if bucket.end_ts_ns > flush_cutoff_ns:
                # Skip buckets still in grace period
                continue

            flushed_keys.append(bucket_start_ns)

            # Flush counters
            for metric_name, counter_data in bucket.counters.items():
                await self._ensure_metric_registered(metric_name, "counter", counter_data.keys())

                counter = self.registry.get_counter(metric_name)
                if counter:
                    for labels_key, value in counter_data.items():
                        counter_labels: dict[str, str] = dict(labels_key)
                        counter.inc(value, counter_labels)
                        lines.append(
                            json.dumps(
                                {
                                    "timestamp_ns": bucket.start_ts_ns,
                                    "metric_name": metric_name,
                                    "metric_type": "counter",
                                    "labels": counter_labels,
                                    "value": value,
                                    "interval_seconds": bucket.interval_seconds,
                                }
                            )
                        )

            # Flush gauges (use average)
            for metric_name, gauge_data in bucket.gauges.items():
                await self._ensure_metric_registered(metric_name, "gauge", gauge_data.keys())

                gauge = self.registry.get_gauge(metric_name)
                if gauge:
                    for labels_key, (sum_val, count) in gauge_data.items():
                        gauge_labels: dict[str, str] = dict(labels_key)
                        avg_value = sum_val / count if count > 0 else 0.0
                        gauge.set(avg_value, gauge_labels)
                        lines.append(
                            json.dumps(
                                {
                                    "timestamp_ns": bucket.start_ts_ns,
                                    "metric_name": metric_name,
                                    "metric_type": "gauge",
                                    "labels": gauge_labels,
                                    "value": avg_value,
                                    "interval_seconds": bucket.interval_seconds,
                                }
                            )
                        )

            # Flush histograms
            for metric_name, histogram_data in bucket.histograms.items():
                await self._ensure_metric_registered(
                    metric_name, "histogram", histogram_data.keys()
                )

                histogram = self.registry.get_histogram(metric_name)
                if histogram:
                    for labels_key, observations in histogram_data.items():
                        histogram_labels: dict[str, str] = dict(labels_key)
                        for obs in observations:
                            histogram.observe(obs, histogram_labels)
                        lines.append(
                            json.dumps(
                                {
                                    "timestamp_ns": bucket.start_ts_ns,
                                    "metric_name": metric_name,
                                    "metric_type": "histogram",
                                    "labels": histogram_labels,
                                    "observations": observations,
                                    "interval_seconds": bucket.interval_seconds,
                                }
                            )
                        )

        for key in flushed_keys:
            self._buckets.pop(key, None)

        return lines

    async def _ensure_metric_registered(
        self, metric_name: str, metric_type: str, labels_keys: Any
    ) -> None:
        """Ensure metric is registered in registry.

        Args:
            metric_name: Metric name
            metric_type: Metric type (counter/gauge/histogram)
            labels_keys: Iterable of label key tuples
        """
        registry_key = (metric_name, metric_type)
        if registry_key in self._registered_metrics:
            return

        # Extract label names from first label key
        label_names: list[str] = []
        if labels_keys:
            first_labels_key = next(iter(labels_keys), ())
            if first_labels_key:
                label_names = [k for k, v in first_labels_key]

        try:
            if metric_type == "counter":
                await self.registry.register_counter(
                    metric_name, f"Aggregated metric {metric_name}", label_names
                )
            elif metric_type == "gauge":
                await self.registry.register_gauge(
                    metric_name, f"Aggregated metric {metric_name}", label_names
                )
            elif metric_type == "histogram":
                # Use default Prometheus histogram buckets
                buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
                await self.registry.register_histogram(
                    metric_name, f"Aggregated metric {metric_name}", buckets, label_names
                )

            self._registered_metrics.add(registry_key)
            logger.debug(
                "telemetry.aggregator_registered_metric",
                extra={"name": metric_name, "type": metric_type, "labels": label_names},
            )
        except ValueError as e:
            # Metric already registered (by another component or previous run)
            logger.debug(
                "telemetry.aggregator_metric_already_registered",
                extra={"name": metric_name, "type": metric_type, "error": str(e)},
            )
            self._registered_metrics.add(registry_key)

    def _flush_to_journal(self, lines: list[str]) -> None:
        """Persist aggregated metrics to journal."""
        if not lines:
            return

        if lines:
            with open(self.journal_path, "a") as f:
                f.write("\n".join(lines) + "\n")

            logger.debug(
                "telemetry.aggregator_flushed_to_journal",
                extra={"records": len(lines), "path": str(self.journal_path)},
            )

    def downsample_to_interval(
        self, metrics: list[MetricSnapshot], interval_seconds: int
    ) -> list[MetricSnapshot]:
        """Downsample metrics to interval (avg for gauges, sum for counters).

        Args:
            metrics: List of metric snapshots to downsample
            interval_seconds: Target interval (e.g., 300 for 5-minute buckets)

        Returns:
            List of downsampled metric snapshots
        """
        # Group metrics by time bucket, name, labels, and type
        buckets: dict[tuple[int, str, LabelsKey, str], list[MetricSnapshot]] = defaultdict(list)

        interval_ns = interval_seconds * 1_000_000_000
        for snapshot in metrics:
            bucket_start_ns = (snapshot.timestamp_ns // interval_ns) * interval_ns
            labels_key: LabelsKey = tuple(sorted(snapshot.labels.items()))
            key = (bucket_start_ns, snapshot.name, labels_key, snapshot.metric_type)
            buckets[key].append(snapshot)

        # Aggregate each bucket
        downsampled: list[MetricSnapshot] = []
        for (bucket_start_ns, name, labels_key, metric_type), snapshots in buckets.items():
            labels_dict: dict[str, str] = dict(labels_key)

            if metric_type == "counter":
                # Sum counter values
                total_value = sum(s.value for s in snapshots)
                downsampled.append(
                    MetricSnapshot(
                        name=name,
                        value=total_value,
                        timestamp_ns=bucket_start_ns,
                        labels=labels_dict,
                        metric_type="counter",
                    )
                )
            elif metric_type == "gauge":
                # Average gauge values
                avg_value = sum(s.value for s in snapshots) / len(snapshots)
                downsampled.append(
                    MetricSnapshot(
                        name=name,
                        value=avg_value,
                        timestamp_ns=bucket_start_ns,
                        labels=labels_dict,
                        metric_type="gauge",
                    )
                )
            elif metric_type == "histogram":
                observations = [s.value for s in snapshots]
                for obs in observations:
                    downsampled.append(
                        MetricSnapshot(
                            name=name,
                            value=obs,
                            timestamp_ns=bucket_start_ns,
                            labels=labels_dict,
                            metric_type="histogram",
                        )
                    )

        return downsampled
