"""Tests for Prometheus exporter and metric registry."""

from __future__ import annotations

import asyncio

import pytest

from telemetry.prometheus import PrometheusExporter
from telemetry.registry import Counter, Gauge, Histogram, MetricRegistry
from tests.utils import InMemoryBus


class TestCounter:
    """Tests for Counter metric."""

    def test_creates_counter_without_labels(self) -> None:
        """Test creating counter without labels."""
        counter = Counter("test_counter", "Test counter")

        assert counter.name == "test_counter"
        assert counter.help_text == "Test counter"
        assert counter.label_names == []

    def test_increments_counter_without_labels(self) -> None:
        """Test incrementing counter without labels."""
        counter = Counter("test_counter", "Test counter")

        counter.inc()
        assert counter.get() == 1.0

        counter.inc(5.0)
        assert counter.get() == 6.0

    def test_increments_counter_with_labels(self) -> None:
        """Test incrementing counter with labels."""
        counter = Counter("test_counter", "Test counter", ["strategy_id", "symbol"])

        counter.inc(1.0, {"strategy_id": "twap_v1", "symbol": "BTC/USDT"})
        counter.inc(2.0, {"strategy_id": "twap_v1", "symbol": "BTC/USDT"})
        counter.inc(1.0, {"strategy_id": "vwap_v1", "symbol": "ETH/USDT"})

        assert counter.get({"strategy_id": "twap_v1", "symbol": "BTC/USDT"}) == 3.0
        assert counter.get({"strategy_id": "vwap_v1", "symbol": "ETH/USDT"}) == 1.0

    def test_rejects_negative_increment(self) -> None:
        """Test counter rejects negative increment."""
        counter = Counter("test_counter", "Test counter")

        with pytest.raises(ValueError, match="Counter can only increase"):
            counter.inc(-1.0)

    def test_rejects_missing_labels(self) -> None:
        """Test counter rejects missing labels."""
        counter = Counter("test_counter", "Test counter", ["strategy_id"])

        with pytest.raises(ValueError, match="requires labels"):
            counter.inc()

    def test_rejects_extra_labels(self) -> None:
        """Test counter rejects extra labels."""
        counter = Counter("test_counter", "Test counter")

        with pytest.raises(ValueError, match="has no labels"):
            counter.inc(labels={"strategy_id": "test"})

    def test_rejects_mismatched_labels(self) -> None:
        """Test counter rejects mismatched label keys."""
        counter = Counter("test_counter", "Test counter", ["strategy_id", "symbol"])

        with pytest.raises(ValueError, match="don't match expected"):
            counter.inc(labels={"strategy_id": "test", "wrong_key": "value"})

    def test_collects_samples(self) -> None:
        """Test counter collect() returns all label combinations."""
        counter = Counter("test_counter", "Test counter", ["strategy_id"])

        counter.inc(1.0, {"strategy_id": "strategy_a"})
        counter.inc(2.0, {"strategy_id": "strategy_b"})

        samples = counter.collect()
        assert len(samples) == 2
        assert ({"strategy_id": "strategy_a"}, 1.0) in samples
        assert ({"strategy_id": "strategy_b"}, 2.0) in samples


class TestGauge:
    """Tests for Gauge metric."""

    def test_sets_gauge_value(self) -> None:
        """Test setting gauge value."""
        gauge = Gauge("test_gauge", "Test gauge")

        gauge.set(42.5)
        assert gauge.get() == 42.5

        gauge.set(10.0)
        assert gauge.get() == 10.0

    def test_increments_and_decrements_gauge(self) -> None:
        """Test incrementing and decrementing gauge."""
        gauge = Gauge("test_gauge", "Test gauge")

        gauge.inc()
        assert gauge.get() == 1.0

        gauge.inc(5.0)
        assert gauge.get() == 6.0

        gauge.dec(2.0)
        assert gauge.get() == 4.0

        gauge.dec()
        assert gauge.get() == 3.0

    def test_gauge_with_labels(self) -> None:
        """Test gauge with labels."""
        gauge = Gauge("test_gauge", "Test gauge", ["portfolio_id"])

        gauge.set(1000.0, {"portfolio_id": "portfolio_a"})
        gauge.set(2000.0, {"portfolio_id": "portfolio_b"})

        assert gauge.get({"portfolio_id": "portfolio_a"}) == 1000.0
        assert gauge.get({"portfolio_id": "portfolio_b"}) == 2000.0

    def test_gauge_collects_samples(self) -> None:
        """Test gauge collect() returns all label combinations."""
        gauge = Gauge("test_gauge", "Test gauge", ["symbol"])

        gauge.set(100.0, {"symbol": "BTC/USDT"})
        gauge.set(200.0, {"symbol": "ETH/USDT"})

        samples = gauge.collect()
        assert len(samples) == 2
        assert ({"symbol": "BTC/USDT"}, 100.0) in samples
        assert ({"symbol": "ETH/USDT"}, 200.0) in samples


class TestHistogram:
    """Tests for Histogram metric."""

    def test_creates_histogram_with_sorted_buckets(self) -> None:
        """Test creating histogram with sorted buckets."""
        histogram = Histogram("test_histogram", "Test histogram", [0.1, 0.5, 1.0, 5.0])

        assert histogram.name == "test_histogram"
        assert histogram.buckets == [0.1, 0.5, 1.0, 5.0]

    def test_rejects_empty_buckets(self) -> None:
        """Test histogram rejects empty buckets."""
        with pytest.raises(ValueError, match="buckets must not be empty"):
            Histogram("test_histogram", "Test histogram", [])

    def test_rejects_unsorted_buckets(self) -> None:
        """Test histogram rejects unsorted buckets."""
        with pytest.raises(ValueError, match="buckets must be sorted"):
            Histogram("test_histogram", "Test histogram", [1.0, 0.5, 5.0])

    def test_observes_values(self) -> None:
        """Test histogram observes values and updates buckets."""
        histogram = Histogram("test_histogram", "Test histogram", [1.0, 5.0, 10.0])

        histogram.observe(0.5)  # Falls in bucket 1.0
        histogram.observe(3.0)  # Falls in bucket 5.0
        histogram.observe(7.0)  # Falls in bucket 10.0
        histogram.observe(15.0)  # Falls in no bucket (>10.0)

        data = histogram.get()
        assert data["bucket_counts"] == [1, 2, 3]  # Cumulative counts
        assert data["sum"] == 25.5
        assert data["count"] == 4

    def test_histogram_with_labels(self) -> None:
        """Test histogram with labels."""
        histogram = Histogram("test_histogram", "Test histogram", [0.1, 1.0], ["strategy_id"])

        histogram.observe(0.05, {"strategy_id": "strategy_a"})
        histogram.observe(0.5, {"strategy_id": "strategy_a"})
        histogram.observe(2.0, {"strategy_id": "strategy_b"})

        data_a = histogram.get({"strategy_id": "strategy_a"})
        assert data_a["bucket_counts"] == [1, 2]
        assert data_a["count"] == 2

        data_b = histogram.get({"strategy_id": "strategy_b"})
        assert data_b["bucket_counts"] == [0, 0]
        assert data_b["count"] == 1

    def test_histogram_collects_samples(self) -> None:
        """Test histogram collect() returns all data."""
        histogram = Histogram("test_histogram", "Test histogram", [1.0], ["symbol"])

        histogram.observe(0.5, {"symbol": "BTC/USDT"})
        histogram.observe(2.0, {"symbol": "ETH/USDT"})

        samples = histogram.collect()
        assert len(samples) == 2

        # Check BTC/USDT sample
        btc_sample = next(s for s in samples if s[0] == {"symbol": "BTC/USDT"})
        assert btc_sample[1] == [1]  # bucket_counts
        assert btc_sample[2] == 0.5  # sum
        assert btc_sample[3] == 1  # count


class TestMetricRegistry:
    """Tests for MetricRegistry."""

    @pytest.mark.asyncio
    async def test_registers_counter(self) -> None:
        """Test registering counter."""
        registry = MetricRegistry()

        counter = await registry.register_counter("test_counter", "Test counter", ["label1"])

        assert isinstance(counter, Counter)
        assert registry.get_counter("test_counter") == counter

    @pytest.mark.asyncio
    async def test_registers_gauge(self) -> None:
        """Test registering gauge."""
        registry = MetricRegistry()

        gauge = await registry.register_gauge("test_gauge", "Test gauge")

        assert isinstance(gauge, Gauge)
        assert registry.get_gauge("test_gauge") == gauge

    @pytest.mark.asyncio
    async def test_registers_histogram(self) -> None:
        """Test registering histogram."""
        registry = MetricRegistry()

        histogram = await registry.register_histogram(
            "test_histogram", "Test histogram", [1.0, 5.0]
        )

        assert isinstance(histogram, Histogram)
        assert registry.get_histogram("test_histogram") == histogram

    @pytest.mark.asyncio
    async def test_rejects_duplicate_counter_registration(self) -> None:
        """Test registry rejects duplicate counter registration."""
        registry = MetricRegistry()

        await registry.register_counter("test_counter", "Test counter")

        with pytest.raises(ValueError, match="already registered"):
            await registry.register_counter("test_counter", "Duplicate")

    @pytest.mark.asyncio
    async def test_rejects_same_name_different_type(self) -> None:
        """Test registry rejects same name for different metric types."""
        registry = MetricRegistry()

        await registry.register_counter("test_metric", "Test metric")

        with pytest.raises(ValueError, match="already registered as different type"):
            await registry.register_gauge("test_metric", "Test metric")

    @pytest.mark.asyncio
    async def test_collects_all_metrics(self) -> None:
        """Test collect_all() returns all metrics."""
        registry = MetricRegistry()

        counter = await registry.register_counter("test_counter", "Counter")
        gauge = await registry.register_gauge("test_gauge", "Gauge")
        histogram = await registry.register_histogram("test_histogram", "Histogram", [1.0])

        all_metrics = registry.collect_all()

        assert all_metrics["counters"]["test_counter"] == counter
        assert all_metrics["gauges"]["test_gauge"] == gauge
        assert all_metrics["histograms"]["test_histogram"] == histogram


class TestPrometheusExporter:
    """Tests for PrometheusExporter."""

    @pytest.mark.asyncio
    async def test_starts_and_stops_http_server(self) -> None:
        """Test starting and stopping HTTP server."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19090, bind_host="127.0.0.1")

        await exporter.start()
        assert exporter._server is not None

        await exporter.stop()
        assert exporter._server is None

    @pytest.mark.asyncio
    async def test_serves_metrics_at_metrics_endpoint(self) -> None:
        """Test /metrics endpoint serves metrics."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19091, bind_host="127.0.0.1")

        await exporter.start()

        try:
            # Register a counter and increment it
            counter = await exporter.register_counter("test_counter_total", "Test counter")
            counter.inc(42.0)

            # Fetch metrics via HTTP
            response = await self._http_get("127.0.0.1", 19091, "/metrics")

            assert "HTTP/1.1 200 OK" in response
            assert "# HELP test_counter_total Test counter" in response
            assert "# TYPE test_counter_total counter" in response
            assert "test_counter_total 42.0" in response

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_path(self) -> None:
        """Test returns 404 for unknown paths."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19092, bind_host="127.0.0.1")

        await exporter.start()

        try:
            response = await self._http_get("127.0.0.1", 19092, "/unknown")
            assert "HTTP/1.1 404 Not Found" in response

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_requires_bearer_token_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test requires Bearer token authentication when NJORD_METRICS_TOKEN is set."""
        monkeypatch.setenv("NJORD_METRICS_TOKEN", "secret123")

        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19093, bind_host="127.0.0.1")

        await exporter.start()

        try:
            # Request without token should fail
            response = await self._http_get("127.0.0.1", 19093, "/metrics")
            assert "HTTP/1.1 401 Unauthorized" in response

            # Request with correct token should succeed
            response = await self._http_get(
                "127.0.0.1", 19093, "/metrics", headers={"Authorization": "Bearer secret123"}
            )
            assert "HTTP/1.1 200 OK" in response

            # Request with wrong token should fail
            response = await self._http_get(
                "127.0.0.1", 19093, "/metrics", headers={"Authorization": "Bearer wrong"}
            )
            assert "HTTP/1.1 401 Unauthorized" in response

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_formats_counter_in_exposition_format(self) -> None:
        """Test counter formatting in Prometheus exposition format."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19094, bind_host="127.0.0.1")

        await exporter.start()

        try:
            counter = await exporter.register_counter(
                "njord_orders_total", "Total orders", ["strategy_id", "symbol"]
            )
            counter.inc(5.0, {"strategy_id": "twap_v1", "symbol": "BTC/USDT"})
            counter.inc(3.0, {"strategy_id": "vwap_v1", "symbol": "ETH/USDT"})

            response = await self._http_get("127.0.0.1", 19094, "/metrics")

            assert "# HELP njord_orders_total Total orders" in response
            assert "# TYPE njord_orders_total counter" in response
            assert 'njord_orders_total{strategy_id="twap_v1",symbol="BTC/USDT"} 5.0' in response
            assert 'njord_orders_total{strategy_id="vwap_v1",symbol="ETH/USDT"} 3.0' in response

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_formats_gauge_in_exposition_format(self) -> None:
        """Test gauge formatting in Prometheus exposition format."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19095, bind_host="127.0.0.1")

        await exporter.start()

        try:
            gauge = await exporter.register_gauge("njord_active_positions", "Active positions")
            gauge.set(10.0)

            response = await self._http_get("127.0.0.1", 19095, "/metrics")

            assert "# HELP njord_active_positions Active positions" in response
            assert "# TYPE njord_active_positions gauge" in response
            assert "njord_active_positions 10.0" in response

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_formats_histogram_in_exposition_format(self) -> None:
        """Test histogram formatting in Prometheus exposition format."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19096, bind_host="127.0.0.1")

        await exporter.start()

        try:
            histogram = await exporter.register_histogram(
                "njord_latency_seconds", "Latency in seconds", [0.1, 0.5, 1.0]
            )
            histogram.observe(0.05)
            histogram.observe(0.3)
            histogram.observe(0.8)

            response = await self._http_get("127.0.0.1", 19096, "/metrics")

            assert "# HELP njord_latency_seconds Latency in seconds" in response
            assert "# TYPE njord_latency_seconds histogram" in response
            assert 'njord_latency_seconds_bucket{le="0.1"} 1' in response
            assert 'njord_latency_seconds_bucket{le="0.5"} 2' in response
            assert 'njord_latency_seconds_bucket{le="1.0"} 3' in response
            assert 'njord_latency_seconds_bucket{le="+Inf"} 3' in response
            assert "njord_latency_seconds_sum 1.15" in response
            assert "njord_latency_seconds_count 3" in response

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_counter_persists_across_scrapes(self) -> None:
        """Test counter values persist across multiple scrapes."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19097, bind_host="127.0.0.1")

        await exporter.start()

        try:
            counter = await exporter.register_counter("test_counter_total", "Test counter")
            counter.inc(10.0)

            # First scrape
            response1 = await self._http_get("127.0.0.1", 19097, "/metrics")
            assert "test_counter_total 10.0" in response1

            # Increment counter
            counter.inc(5.0)

            # Second scrape should show updated value
            response2 = await self._http_get("127.0.0.1", 19097, "/metrics")
            assert "test_counter_total 15.0" in response2

        finally:
            await exporter.stop()

    @pytest.mark.asyncio
    async def test_gauge_reflects_latest_value(self) -> None:
        """Test gauge reflects latest value."""
        bus = InMemoryBus()
        exporter = PrometheusExporter(bus, port=19098, bind_host="127.0.0.1")

        await exporter.start()

        try:
            gauge = await exporter.register_gauge("test_gauge", "Test gauge")
            gauge.set(100.0)

            response1 = await self._http_get("127.0.0.1", 19098, "/metrics")
            assert "test_gauge 100.0" in response1

            gauge.set(50.0)

            response2 = await self._http_get("127.0.0.1", 19098, "/metrics")
            assert "test_gauge 50.0" in response2

        finally:
            await exporter.stop()

    async def _http_get(
        self, host: str, port: int, path: str, headers: dict[str, str] | None = None
    ) -> str:
        """Send HTTP GET request.

        Args:
            host: Host to connect to
            port: Port to connect to
            path: Request path
            headers: Optional headers

        Returns:
            HTTP response as string
        """
        reader, writer = await asyncio.open_connection(host, port)

        try:
            # Build request
            request = f"GET {path} HTTP/1.1\r\n"
            request += f"Host: {host}\r\n"
            if headers:
                for key, value in headers.items():
                    request += f"{key}: {value}\r\n"
            request += "\r\n"

            # Send request
            writer.write(request.encode("utf-8"))
            await writer.drain()

            # Read response
            response_bytes = await reader.read(8192)
            return response_bytes.decode("utf-8")

        finally:
            writer.close()
            await writer.wait_closed()
