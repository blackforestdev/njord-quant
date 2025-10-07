"""Prometheus metrics exporter with HTTP endpoint."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from typing import TYPE_CHECKING

from telemetry.contracts import MetricSnapshot
from telemetry.registry import Counter, Gauge, Histogram, MetricRegistry, Summary

if TYPE_CHECKING:
    from core.bus import BusProto


class PrometheusExporter:
    """Prometheus-compatible metrics HTTP exporter.

    Exposes metrics at /metrics endpoint in Prometheus text exposition format.
    """

    def __init__(
        self,
        bus: BusProto,
        port: int = 9090,
        bind_host: str = "127.0.0.1",
        registry: MetricRegistry | None = None,
    ) -> None:
        """Initialize Prometheus exporter.

        Args:
            bus: Event bus instance (for future metric aggregation)
            port: HTTP port to bind to
            bind_host: Host to bind to (defaults to localhost for security)
            registry: Metric registry (creates new if None)
        """
        self.bus = bus
        self.port = port
        self.bind_host = bind_host
        self.registry = registry or MetricRegistry()
        self._server: asyncio.Server | None = None
        self._bearer_token = os.getenv("NJORD_METRICS_TOKEN")
        self._metrics_task: asyncio.Task[None] | None = None
        self._metrics_topic = "telemetry.metrics"
        self._logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """Start HTTP server for /metrics endpoint.

        Security:
            - Binds to localhost (127.0.0.1) by default
            - Optional Bearer token auth via NJORD_METRICS_TOKEN env var
        """
        self._server = await asyncio.start_server(self._handle_client, self.bind_host, self.port)
        await self._start_consumer()

    async def stop(self) -> None:
        """Stop HTTP server."""
        await self._stop_consumer()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _start_consumer(self) -> None:
        """Start background task consuming metric snapshots from the bus."""
        if self._metrics_task is None:
            self._metrics_task = asyncio.create_task(self._consume_metrics())

    async def _stop_consumer(self) -> None:
        """Stop background metric consumption."""
        if self._metrics_task is None:
            return

        task = self._metrics_task
        self._metrics_task = None
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _consume_metrics(self) -> None:
        """Consume metric snapshots from the bus and update the registry."""
        try:
            async for payload in self.bus.subscribe(self._metrics_topic):
                snapshot = self._deserialize_snapshot(payload)
                if snapshot is None:
                    continue
                try:
                    await self._apply_snapshot(snapshot)
                except Exception:
                    self._logger.exception(
                        "telemetry.metrics.apply_failed",
                        extra={
                            "metric_name": snapshot.name,
                            "metric_type": snapshot.metric_type,
                        },
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("telemetry.metrics.consumer_error")

    def _deserialize_snapshot(self, payload: object) -> MetricSnapshot | None:
        if not isinstance(payload, dict):
            self._logger.warning(
                "telemetry.metrics.invalid_payload_type",
                extra={"payload_type": type(payload).__name__},
            )
            return None

        try:
            return MetricSnapshot.from_dict(payload)
        except (KeyError, ValueError, TypeError) as exc:
            self._logger.warning(
                "telemetry.metrics.invalid_snapshot",
                extra={"error": str(exc), "payload_keys": list(payload.keys())},
            )
            return None

    async def _apply_snapshot(self, snapshot: MetricSnapshot) -> None:
        labels = dict(snapshot.labels)
        metric_type = snapshot.metric_type

        if metric_type == "counter":
            counter = self.registry.get_counter(snapshot.name)
            if counter is None:
                self._logger.warning(
                    "telemetry.metrics.unregistered_metric",
                    extra={"metric_name": snapshot.name, "metric_type": metric_type},
                )
                return
            counter.inc(snapshot.value, labels or None)
            return

        if metric_type == "gauge":
            gauge = self.registry.get_gauge(snapshot.name)
            if gauge is None:
                self._logger.warning(
                    "telemetry.metrics.unregistered_metric",
                    extra={"metric_name": snapshot.name, "metric_type": metric_type},
                )
                return
            gauge.set(snapshot.value, labels or None)
            return

        if metric_type == "histogram":
            histogram = self.registry.get_histogram(snapshot.name)
            if histogram is None:
                self._logger.warning(
                    "telemetry.metrics.unregistered_metric",
                    extra={"metric_name": snapshot.name, "metric_type": metric_type},
                )
                return
            histogram.observe(snapshot.value, labels or None)
            return

        if metric_type == "summary":
            summary = self.registry.get_summary(snapshot.name)
            if summary is None:
                self._logger.warning(
                    "telemetry.metrics.unregistered_metric",
                    extra={"metric_name": snapshot.name, "metric_type": metric_type},
                )
                return
            summary.observe(snapshot.value, labels or None)
            return

        self._logger.warning(
            "telemetry.metrics.unsupported_type",
            extra={"metric_name": snapshot.name, "metric_type": metric_type},
        )

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle HTTP client connection.

        Args:
            reader: Stream reader
            writer: Stream writer
        """
        try:
            # Read HTTP request line
            request_line = await reader.readline()
            if not request_line:
                return

            request_str = request_line.decode("utf-8").strip()
            parts = request_str.split()
            if len(parts) < 2:
                await self._send_response(writer, 400, "Bad Request")
                return

            method, path = parts[0], parts[1]

            # Read headers
            headers = await self._read_headers(reader)

            # Check authentication if token is configured
            if self._bearer_token:
                auth_header = headers.get("authorization", "")
                expected_auth = f"Bearer {self._bearer_token}"
                if auth_header != expected_auth:
                    await self._send_response(writer, 401, "Unauthorized")
                    return

            # Route request
            if method == "GET" and path == "/metrics":
                metrics_text = await self.collect_metrics()
                await self._send_response(writer, 200, metrics_text, content_type="text/plain")
            else:
                await self._send_response(writer, 404, "Not Found")

        except Exception:
            await self._send_response(writer, 500, "Internal Server Error")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _read_headers(self, reader: asyncio.StreamReader) -> dict[str, str]:
        """Read HTTP headers.

        Args:
            reader: Stream reader

        Returns:
            Dictionary of headers (lowercase keys)
        """
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n":
                break

            header_str = line.decode("utf-8").strip()
            if ":" in header_str:
                key, value = header_str.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        return headers

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        body: str,
        content_type: str = "text/plain",
    ) -> None:
        """Send HTTP response.

        Args:
            writer: Stream writer
            status_code: HTTP status code
            body: Response body
            content_type: Content-Type header
        """
        status_messages = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
            500: "Internal Server Error",
        }
        status_message = status_messages.get(status_code, "Unknown")

        response = (
            f"HTTP/1.1 {status_code} {status_message}\r\n"
            f"Content-Type: {content_type}; charset=utf-8\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )

        writer.write(response.encode("utf-8"))
        await writer.drain()

    async def collect_metrics(self) -> str:
        """Collect all metrics and format for Prometheus.

        Returns:
            Metrics in Prometheus text exposition format
        """
        lines: list[str] = []
        all_metrics = self.registry.collect_all()

        # Counters
        for name, counter in all_metrics["counters"].items():
            lines.append(f"# HELP {name} {counter.help_text}")
            lines.append(f"# TYPE {name} counter")
            samples = counter.collect()
            if not samples:
                # If no samples, output default value
                lines.append(f"{name} 0.0")
            else:
                for labels_dict, value in samples:
                    label_str = self._format_labels(labels_dict)
                    lines.append(f"{name}{label_str} {value}")

        # Gauges
        for name, gauge in all_metrics["gauges"].items():
            lines.append(f"# HELP {name} {gauge.help_text}")
            lines.append(f"# TYPE {name} gauge")
            samples = gauge.collect()
            if not samples:
                # If no samples, output default value
                lines.append(f"{name} 0.0")
            else:
                for labels_dict, value in samples:
                    label_str = self._format_labels(labels_dict)
                    lines.append(f"{name}{label_str} {value}")

        # Histograms
        for name, histogram in all_metrics["histograms"].items():
            lines.append(f"# HELP {name} {histogram.help_text}")
            lines.append(f"# TYPE {name} histogram")
            samples = histogram.collect()
            if not samples:
                # If no samples, output defaults
                lines.append(f"{name}_count 0")
                lines.append(f"{name}_sum 0.0")
            else:
                for labels_dict, bucket_counts, sum_val, count_val in samples:
                    # Bucket samples
                    for i, upper_bound in enumerate(histogram.buckets):
                        bucket_labels = {**labels_dict, "le": str(upper_bound)}
                        label_str = self._format_labels(bucket_labels)
                        cumulative_count = bucket_counts[i]
                        lines.append(f"{name}_bucket{label_str} {cumulative_count}")

                    # +Inf bucket (all observations)
                    inf_labels = {**labels_dict, "le": "+Inf"}
                    label_str = self._format_labels(inf_labels)
                    lines.append(f"{name}_bucket{label_str} {count_val}")

                    # Sum and count
                    base_label_str = self._format_labels(labels_dict)
                    lines.append(f"{name}_sum{base_label_str} {sum_val}")
                    lines.append(f"{name}_count{base_label_str} {count_val}")

        # Summaries
        for name, summary in all_metrics["summaries"].items():
            lines.append(f"# HELP {name} {summary.help_text}")
            lines.append(f"# TYPE {name} summary")
            samples = summary.collect()
            if not samples:
                base_label_str = self._format_labels({})
                lines.append(f"{name}_count{base_label_str} 0")
                lines.append(f"{name}_sum{base_label_str} 0.0")
                continue

            for labels_dict, quantiles, sum_val, count_val in samples:
                for quantile, value in quantiles.items():
                    labels_with_quantile = {**labels_dict, "quantile": f"{quantile:.2f}"}
                    label_str = self._format_labels(labels_with_quantile)
                    lines.append(f"{name}{label_str} {value}")

                base_label_str = self._format_labels(labels_dict)
                lines.append(f"{name}_sum{base_label_str} {sum_val}")
                lines.append(f"{name}_count{base_label_str} {count_val}")

        # Add final newline
        return "\n".join(lines) + "\n" if lines else ""

    def _format_labels(self, labels: dict[str, str]) -> str:
        """Format labels for Prometheus exposition format.

        Args:
            labels: Label dictionary

        Returns:
            Formatted label string (e.g., '{key1="val1",key2="val2"}')
        """
        if not labels:
            return ""

        # Sort labels for deterministic output
        sorted_labels = sorted(labels.items())
        label_parts = [f'{key}="{value}"' for key, value in sorted_labels]
        return "{" + ",".join(label_parts) + "}"

    async def register_counter(
        self, name: str, help_text: str, labels: list[str] | None = None
    ) -> Counter:
        """Register a counter metric.

        Args:
            name: Metric name
            help_text: Help text
            labels: Label names

        Returns:
            Counter instance
        """
        return await self.registry.register_counter(name, help_text, labels)

    async def register_gauge(
        self, name: str, help_text: str, labels: list[str] | None = None
    ) -> Gauge:
        """Register a gauge metric.

        Args:
            name: Metric name
            help_text: Help text
            labels: Label names

        Returns:
            Gauge instance
        """
        return await self.registry.register_gauge(name, help_text, labels)

    async def register_histogram(
        self, name: str, help_text: str, buckets: list[float], labels: list[str] | None = None
    ) -> Histogram:
        """Register a histogram metric.

        Args:
            name: Metric name
            help_text: Help text
            buckets: Bucket boundaries
            labels: Label names

        Returns:
            Histogram instance
        """
        return await self.registry.register_histogram(name, help_text, buckets, labels)

    async def register_summary(
        self,
        name: str,
        help_text: str,
        quantiles: list[float] | None = None,
        labels: list[str] | None = None,
    ) -> Summary:
        """Register a summary metric."""
        return await self.registry.register_summary(name, help_text, quantiles, labels)
