"""Tests for metric aggregation service."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from telemetry.aggregation import AggregationBucket, MetricAggregator
from telemetry.contracts import MetricSnapshot
from telemetry.registry import MetricRegistry
from tests.utils import InMemoryBus


class TestAggregationBucket:
    """Tests for AggregationBucket."""

    def test_bucket_time_range(self) -> None:
        """Test bucket contains correct time range."""
        start_ns = 1_000_000_000_000_000_000
        bucket = AggregationBucket(start_ts_ns=start_ns, interval_seconds=60)

        assert bucket.start_ts_ns == start_ns
        assert bucket.end_ts_ns == start_ns + 60_000_000_000
        assert bucket.interval_seconds == 60

    def test_bucket_contains_timestamp(self) -> None:
        """Test bucket.contains() correctly identifies timestamps."""
        start_ns = 1_000_000_000_000_000_000
        bucket = AggregationBucket(start_ts_ns=start_ns, interval_seconds=60)

        # Timestamp within bucket
        assert bucket.contains(start_ns + 30_000_000_000)

        # Timestamp at start boundary (inclusive)
        assert bucket.contains(start_ns)

        # Timestamp at end boundary (exclusive)
        assert not bucket.contains(bucket.end_ts_ns)

        # Timestamp before bucket
        assert not bucket.contains(start_ns - 1_000_000_000)

        # Timestamp after bucket
        assert not bucket.contains(bucket.end_ts_ns + 1_000_000_000)

    def test_add_counter_metric(self) -> None:
        """Test adding counter metrics to bucket."""
        bucket = AggregationBucket(start_ts_ns=1_000_000_000_000_000_000, interval_seconds=60)

        snapshot1 = MetricSnapshot(
            name="requests_total",
            value=5.0,
            timestamp_ns=bucket.start_ts_ns + 10_000_000_000,
            labels={"service": "api"},
            metric_type="counter",
        )

        snapshot2 = MetricSnapshot(
            name="requests_total",
            value=3.0,
            timestamp_ns=bucket.start_ts_ns + 20_000_000_000,
            labels={"service": "api"},
            metric_type="counter",
        )

        bucket.add_metric(snapshot1)
        bucket.add_metric(snapshot2)

        # Counter values should be summed
        labels_key = tuple(sorted(snapshot1.labels.items()))
        assert bucket.counters["requests_total"][labels_key] == 8.0

    def test_add_gauge_metric(self) -> None:
        """Test adding gauge metrics to bucket."""
        bucket = AggregationBucket(start_ts_ns=1_000_000_000_000_000_000, interval_seconds=60)

        snapshot1 = MetricSnapshot(
            name="memory_usage",
            value=100.0,
            timestamp_ns=bucket.start_ts_ns + 10_000_000_000,
            labels={"service": "api"},
            metric_type="gauge",
        )

        snapshot2 = MetricSnapshot(
            name="memory_usage",
            value=150.0,
            timestamp_ns=bucket.start_ts_ns + 20_000_000_000,
            labels={"service": "api"},
            metric_type="gauge",
        )

        bucket.add_metric(snapshot1)
        bucket.add_metric(snapshot2)

        # Gauge values stored as (sum, count) for averaging
        labels_key = tuple(sorted(snapshot1.labels.items()))
        sum_val, count = bucket.gauges["memory_usage"][labels_key]
        assert sum_val == 250.0
        assert count == 2

    def test_add_histogram_metric(self) -> None:
        """Test adding histogram metrics to bucket."""
        bucket = AggregationBucket(start_ts_ns=1_000_000_000_000_000_000, interval_seconds=60)

        snapshot1 = MetricSnapshot(
            name="request_duration_seconds",
            value=0.05,
            timestamp_ns=bucket.start_ts_ns + 10_000_000_000,
            labels={"endpoint": "/api/v1"},
            metric_type="histogram",
        )

        snapshot2 = MetricSnapshot(
            name="request_duration_seconds",
            value=0.12,
            timestamp_ns=bucket.start_ts_ns + 20_000_000_000,
            labels={"endpoint": "/api/v1"},
            metric_type="histogram",
        )

        bucket.add_metric(snapshot1)
        bucket.add_metric(snapshot2)

        # Histogram observations stored as list
        labels_key = tuple(sorted(snapshot1.labels.items()))
        observations = bucket.histograms["request_duration_seconds"][labels_key]
        assert observations == [0.05, 0.12]


class TestMetricAggregator:
    """Tests for MetricAggregator."""

    @pytest.mark.asyncio
    async def test_aggregator_initialization(self, tmp_path: Path) -> None:
        """Test aggregator initializes correctly."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=24,
        )

        assert aggregator.bus is bus
        assert aggregator.registry is registry
        assert aggregator.retention_hours == 24
        assert aggregator.journal_path.exists()

    @pytest.mark.asyncio
    async def test_aggregate_single_counter_metric(self, tmp_path: Path) -> None:
        """Test aggregating a single counter metric."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus, journal_dir=tmp_path, registry=registry, retention_hours=1
        )

        snapshot = MetricSnapshot(
            name="test_counter_total",
            value=5.0,
            timestamp_ns=time.time_ns(),
            labels={"service": "test"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot)

        # Check bucket was created
        assert len(aggregator._buckets) == 1
        bucket = next(iter(aggregator._buckets.values()))
        labels_key = tuple(sorted(snapshot.labels.items()))
        assert bucket.counters["test_counter_total"][labels_key] == 5.0

    @pytest.mark.asyncio
    async def test_aggregate_multiple_counters_same_bucket(self, tmp_path: Path) -> None:
        """Test aggregating multiple counter metrics into same bucket."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus, journal_dir=tmp_path, registry=registry, retention_hours=1
        )

        base_ts_ns = (time.time_ns() // 60_000_000_000) * 60_000_000_000

        # Two metrics in same 1-minute bucket
        snapshot1 = MetricSnapshot(
            name="requests_total",
            value=10.0,
            timestamp_ns=base_ts_ns,
            labels={"service": "api"},
            metric_type="counter",
        )

        snapshot2 = MetricSnapshot(
            name="requests_total",
            value=15.0,
            timestamp_ns=base_ts_ns + 30_000_000_000,  # +30 seconds
            labels={"service": "api"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot1)
        await aggregator.aggregate_metrics(snapshot2)

        # Should be in same bucket, values summed
        assert len(aggregator._buckets) == 1
        bucket = next(iter(aggregator._buckets.values()))
        labels_key = tuple(sorted(snapshot1.labels.items()))
        assert bucket.counters["requests_total"][labels_key] == 25.0

    @pytest.mark.asyncio
    async def test_aggregate_gauges_calculates_average(self, tmp_path: Path) -> None:
        """Test gauge aggregation stores sum and count for averaging."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus, journal_dir=tmp_path, registry=registry, retention_hours=1
        )

        base_ts_ns = (time.time_ns() // 60_000_000_000) * 60_000_000_000

        snapshot1 = MetricSnapshot(
            name="memory_usage_mb",
            value=100.0,
            timestamp_ns=base_ts_ns,
            labels={"service": "api"},
            metric_type="gauge",
        )

        snapshot2 = MetricSnapshot(
            name="memory_usage_mb",
            value=200.0,
            timestamp_ns=base_ts_ns + 30_000_000_000,
            labels={"service": "api"},
            metric_type="gauge",
        )

        await aggregator.aggregate_metrics(snapshot1)
        await aggregator.aggregate_metrics(snapshot2)

        bucket = next(iter(aggregator._buckets.values()))
        labels_key = tuple(sorted(snapshot1.labels.items()))
        sum_val, count = bucket.gauges["memory_usage_mb"][labels_key]
        assert sum_val == 300.0
        assert count == 2

    @pytest.mark.asyncio
    async def test_metrics_in_different_buckets(self, tmp_path: Path) -> None:
        """Test metrics with timestamps >1 minute apart go to different buckets."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus, journal_dir=tmp_path, registry=registry, retention_hours=1
        )

        base_ts_ns = (time.time_ns() // 60_000_000_000) * 60_000_000_000

        snapshot1 = MetricSnapshot(
            name="requests_total",
            value=10.0,
            timestamp_ns=base_ts_ns,
            labels={"service": "api"},
            metric_type="counter",
        )

        snapshot2 = MetricSnapshot(
            name="requests_total",
            value=15.0,
            timestamp_ns=base_ts_ns + 120_000_000_000,  # +2 minutes
            labels={"service": "api"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot1)
        await aggregator.aggregate_metrics(snapshot2)

        # Should create two buckets
        assert len(aggregator._buckets) == 2

    @pytest.mark.asyncio
    async def test_evict_old_buckets(self, tmp_path: Path) -> None:
        """Test old buckets are evicted beyond retention window."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,  # 1 hour retention
            grace_period_seconds=0,  # No grace period for testing
        )

        now_ns = time.time_ns()
        retention_ns = 1 * 3600 * 1_000_000_000  # 1 hour

        # Add metric from 2 hours ago (beyond retention)
        old_snapshot = MetricSnapshot(
            name="old_metric",
            value=1.0,
            timestamp_ns=now_ns - (2 * retention_ns),
            labels={},
            metric_type="counter",
        )

        # Add recent metric
        recent_snapshot = MetricSnapshot(
            name="recent_metric",
            value=1.0,
            timestamp_ns=now_ns,
            labels={},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(old_snapshot)
        await aggregator.aggregate_metrics(recent_snapshot)

        # Old bucket should be auto-evicted during aggregation
        # (beyond retention + grace period)
        assert len(aggregator._buckets) == 1
        bucket = next(iter(aggregator._buckets.values()))
        assert "recent_metric" in bucket.counters
        assert "old_metric" not in bucket.counters

    @pytest.mark.asyncio
    async def test_flush_to_registry_counters(self, tmp_path: Path) -> None:
        """Test flushing counter metrics to registry."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,
            grace_period_seconds=0,  # No grace period for immediate flush
        )

        # Add metric from past (so it's beyond grace period)
        past_ts_ns = time.time_ns() - 600_000_000_000  # 10 minutes ago

        snapshot = MetricSnapshot(
            name="test_counter_total",
            value=10.0,
            timestamp_ns=past_ts_ns,
            labels={"service": "test"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot)

        # Flush to registry
        async with aggregator._lock:
            lines = await aggregator._flush_to_registry()
            aggregator._flush_to_journal(lines)

        # Check counter was registered and incremented
        counter = registry.get_counter("test_counter_total")
        assert counter is not None
        assert counter.get({"service": "test"}) == 10.0
        assert len(aggregator._buckets) == 0

    @pytest.mark.asyncio
    async def test_flush_to_registry_gauges(self, tmp_path: Path) -> None:
        """Test flushing gauge metrics to registry (uses average)."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,
            grace_period_seconds=0,
        )

        # Use aligned timestamp beyond grace period
        past_ts_ns = (time.time_ns() - 600_000_000_000) // 60_000_000_000 * 60_000_000_000

        # Add two gauge observations in same bucket
        snapshot1 = MetricSnapshot(
            name="memory_usage_mb",
            value=100.0,
            timestamp_ns=past_ts_ns,
            labels={"service": "test"},
            metric_type="gauge",
        )

        snapshot2 = MetricSnapshot(
            name="memory_usage_mb",
            value=200.0,
            timestamp_ns=past_ts_ns + 10_000_000_000,  # +10 seconds, same bucket
            labels={"service": "test"},
            metric_type="gauge",
        )

        await aggregator.aggregate_metrics(snapshot1)
        await aggregator.aggregate_metrics(snapshot2)

        # Flush to registry
        async with aggregator._lock:
            lines = await aggregator._flush_to_registry()
            aggregator._flush_to_journal(lines)

        # Check gauge was set to average
        gauge = registry.get_gauge("memory_usage_mb")
        assert gauge is not None
        assert gauge.get({"service": "test"}) == 150.0  # (100 + 200) / 2
        assert len(aggregator._buckets) == 0

    @pytest.mark.asyncio
    async def test_flush_to_registry_histograms(self, tmp_path: Path) -> None:
        """Test flushing histogram metrics to registry."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,
            grace_period_seconds=0,
        )

        # Use aligned timestamp beyond grace period
        past_ts_ns = (time.time_ns() - 600_000_000_000) // 60_000_000_000 * 60_000_000_000

        snapshot1 = MetricSnapshot(
            name="latency_seconds",
            value=0.05,
            timestamp_ns=past_ts_ns,
            labels={"endpoint": "/api"},
            metric_type="histogram",
        )

        snapshot2 = MetricSnapshot(
            name="latency_seconds",
            value=0.15,
            timestamp_ns=past_ts_ns + 10_000_000_000,  # +10 seconds, same bucket
            labels={"endpoint": "/api"},
            metric_type="histogram",
        )

        await aggregator.aggregate_metrics(snapshot1)
        await aggregator.aggregate_metrics(snapshot2)

        # Flush to registry
        async with aggregator._lock:
            lines = await aggregator._flush_to_registry()
            aggregator._flush_to_journal(lines)

        # Check histogram was registered and observations recorded
        histogram = registry.get_histogram("latency_seconds")
        assert histogram is not None
        data = histogram.get({"endpoint": "/api"})
        assert data["count"] == 2
        assert data["sum"] == 0.20  # 0.05 + 0.15
        assert len(aggregator._buckets) == 0

        parsed_lines = [json.loads(line) for line in lines]
        hist_records = [record for record in parsed_lines if record["metric_type"] == "histogram"]
        assert hist_records
        assert hist_records[0]["observations"] == [0.05, 0.15]

    @pytest.mark.asyncio
    async def test_grace_period_prevents_premature_flush(self, tmp_path: Path) -> None:
        """Test grace period prevents flushing recent metrics."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,
            grace_period_seconds=300,  # 5 minute grace period
        )

        # Add recent metric (within grace period)
        recent_ts_ns = time.time_ns() - 60_000_000_000  # 1 minute ago

        snapshot = MetricSnapshot(
            name="recent_counter",
            value=5.0,
            timestamp_ns=recent_ts_ns,
            labels={"service": "test"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot)

        # Flush to registry
        async with aggregator._lock:
            lines = await aggregator._flush_to_registry()
            aggregator._flush_to_journal(lines)

        # Metric should NOT be flushed (still in grace period)
        counter = registry.get_counter("recent_counter")
        assert counter is None  # Not registered yet
        assert len(aggregator._buckets) == 1

    @pytest.mark.asyncio
    async def test_flush_to_journal(self, tmp_path: Path) -> None:
        """Test flushing metrics to journal file."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,
            grace_period_seconds=0,
        )

        past_ts_ns = time.time_ns() - 600_000_000_000

        snapshot = MetricSnapshot(
            name="test_counter",
            value=10.0,
            timestamp_ns=past_ts_ns,
            labels={"service": "test"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot)

        # Flush to journal
        lines = [
            json.dumps(
                {
                    "timestamp_ns": past_ts_ns,
                    "metric_name": "test_counter",
                    "metric_type": "counter",
                    "labels": {"service": "test"},
                    "value": 10.0,
                    "interval_seconds": 60,
                }
            )
        ]
        aggregator._flush_to_journal(lines)

        # Check journal file was written
        assert aggregator.journal_path.exists()
        content = aggregator.journal_path.read_text().strip()
        assert content

        record = json.loads(content)
        assert record["metric_name"] == "test_counter"
        assert record["metric_type"] == "counter"
        assert record["value"] == 10.0
        assert record["labels"] == {"service": "test"}


class TestMetricDownsampling:
    """Tests for metric downsampling."""

    @pytest.mark.asyncio
    async def test_downsample_counters_sum(self, tmp_path: Path) -> None:
        """Test downsampling counters sums values."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(bus=bus, journal_dir=tmp_path, registry=registry)

        # Use timestamp aligned to 5-minute boundary
        base_ts_ns = (1_000_000_000_000_000_000 // 300_000_000_000) * 300_000_000_000

        # Three counter snapshots in 5-minute window
        metrics = [
            MetricSnapshot(
                name="requests_total",
                value=10.0,
                timestamp_ns=base_ts_ns,
                labels={"service": "api"},
                metric_type="counter",
            ),
            MetricSnapshot(
                name="requests_total",
                value=15.0,
                timestamp_ns=base_ts_ns + 120_000_000_000,  # +2 minutes
                labels={"service": "api"},
                metric_type="counter",
            ),
            MetricSnapshot(
                name="requests_total",
                value=20.0,
                timestamp_ns=base_ts_ns + 240_000_000_000,  # +4 minutes
                labels={"service": "api"},
                metric_type="counter",
            ),
        ]

        # Downsample to 5-minute intervals
        downsampled = aggregator.downsample_to_interval(metrics, interval_seconds=300)

        # Should result in single aggregated metric
        assert len(downsampled) == 1
        assert downsampled[0].name == "requests_total"
        assert downsampled[0].value == 45.0  # 10 + 15 + 20
        assert downsampled[0].labels == {"service": "api"}

    @pytest.mark.asyncio
    async def test_downsample_gauges_average(self, tmp_path: Path) -> None:
        """Test downsampling gauges averages values."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(bus=bus, journal_dir=tmp_path, registry=registry)

        base_ts_ns = (1_000_000_000_000_000_000 // 60_000_000_000) * 60_000_000_000

        metrics = [
            MetricSnapshot(
                name="memory_usage",
                value=100.0,
                timestamp_ns=base_ts_ns,
                labels={"service": "api"},
                metric_type="gauge",
            ),
            MetricSnapshot(
                name="memory_usage",
                value=200.0,
                timestamp_ns=base_ts_ns + 60_000_000_000,  # +1 minute
                labels={"service": "api"},
                metric_type="gauge",
            ),
            MetricSnapshot(
                name="memory_usage",
                value=150.0,
                timestamp_ns=base_ts_ns + 120_000_000_000,  # +2 minutes
                labels={"service": "api"},
                metric_type="gauge",
            ),
        ]

        # Downsample to 5-minute intervals
        downsampled = aggregator.downsample_to_interval(metrics, interval_seconds=300)

        assert len(downsampled) == 1
        assert downsampled[0].name == "memory_usage"
        assert downsampled[0].value == 150.0  # (100 + 200 + 150) / 3
        assert downsampled[0].labels == {"service": "api"}

    @pytest.mark.asyncio
    async def test_downsample_multiple_buckets(self, tmp_path: Path) -> None:
        """Test downsampling creates multiple buckets for wide time range."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(bus=bus, journal_dir=tmp_path, registry=registry)

        base_ts_ns = (1_000_000_000_000_000_000 // 300_000_000_000) * 300_000_000_000

        # Metrics spanning 10 minutes
        metrics = [
            MetricSnapshot(
                name="requests_total",
                value=10.0,
                timestamp_ns=base_ts_ns,
                labels={"service": "api"},
                metric_type="counter",
            ),
            MetricSnapshot(
                name="requests_total",
                value=20.0,
                timestamp_ns=base_ts_ns + 360_000_000_000,  # +6 minutes
                labels={"service": "api"},
                metric_type="counter",
            ),
        ]

        # Downsample to 5-minute intervals
        downsampled = aggregator.downsample_to_interval(metrics, interval_seconds=300)

        # Should create two buckets
        assert len(downsampled) == 2
        assert downsampled[0].value == 10.0  # First 5-minute bucket
        assert downsampled[1].value == 20.0  # Second 5-minute bucket

    @pytest.mark.asyncio
    async def test_downsample_histograms_aggregates_observations(self, tmp_path: Path) -> None:
        """Test downsampling histograms keeps all observations in bucket."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(bus=bus, journal_dir=tmp_path, registry=registry)

        base_ts_ns = 1_000_000_000_000_000_000

        metrics = [
            MetricSnapshot(
                name="latency_seconds",
                value=0.05,
                timestamp_ns=base_ts_ns,
                labels={"endpoint": "/api"},
                metric_type="histogram",
            ),
            MetricSnapshot(
                name="latency_seconds",
                value=0.15,
                timestamp_ns=base_ts_ns + 30_000_000_000,
                labels={"endpoint": "/api"},
                metric_type="histogram",
            ),
        ]

        downsampled = aggregator.downsample_to_interval(metrics, interval_seconds=300)

        assert len(downsampled) == 2
        values = [snapshot.value for snapshot in downsampled]
        assert values == [0.05, 0.15]
        aligned_ts = (base_ts_ns // 300_000_000_000) * 300_000_000_000
        assert all(s.timestamp_ns == aligned_ts for s in downsampled)


class TestMetricAggregatorIntegration:
    """Integration tests for metric aggregator."""

    @pytest.mark.asyncio
    async def test_end_to_end_aggregation(self, tmp_path: Path) -> None:
        """Test end-to-end: publish metric → aggregate → flush to registry."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=registry,
            retention_hours=1,
            grace_period_seconds=0,
        )

        # Publish metric to bus
        past_ts_ns = time.time_ns() - 600_000_000_000  # 10 minutes ago

        snapshot = MetricSnapshot(
            name="integration_test_counter",
            value=100.0,
            timestamp_ns=past_ts_ns,
            labels={"test": "e2e"},
            metric_type="counter",
        )

        await bus.publish_json("telemetry.metrics", snapshot.to_dict())

        # Process metric from bus
        async for msg in bus.subscribe("telemetry.metrics"):
            received_snapshot = MetricSnapshot.from_dict(msg)
            await aggregator.aggregate_metrics(received_snapshot)
            break  # Process one message

        # Flush to registry
        async with aggregator._lock:
            lines = await aggregator._flush_to_registry()
            aggregator._flush_to_journal(lines)

        # Verify metric in registry
        counter = registry.get_counter("integration_test_counter")
        assert counter is not None
        assert counter.get({"test": "e2e"}) == 100.0
        assert len(aggregator._buckets) == 0

    @pytest.mark.asyncio
    async def test_aggregator_with_exporter_integration(self, tmp_path: Path) -> None:
        """Test aggregator + exporter share same registry."""
        bus = InMemoryBus()
        shared_registry = MetricRegistry()

        # Create aggregator with shared registry
        aggregator = MetricAggregator(
            bus=bus,
            journal_dir=tmp_path,
            registry=shared_registry,
            retention_hours=1,
            grace_period_seconds=0,
        )

        # Add metric and flush
        past_ts_ns = time.time_ns() - 600_000_000_000

        snapshot = MetricSnapshot(
            name="shared_metric",
            value=50.0,
            timestamp_ns=past_ts_ns,
            labels={"source": "aggregator"},
            metric_type="counter",
        )

        await aggregator.aggregate_metrics(snapshot)

        async with aggregator._lock:
            lines = await aggregator._flush_to_registry()
            aggregator._flush_to_journal(lines)

        # PrometheusExporter would read from same registry
        # Verify metric is accessible
        counter = shared_registry.get_counter("shared_metric")
        assert counter is not None

        # Collect all metrics (what exporter would do)
        collected = counter.collect()
        assert len(collected) == 1
        labels_dict, value = collected[0]
        assert labels_dict == {"source": "aggregator"}
        assert value == 50.0
