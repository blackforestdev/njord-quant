"""Instrumentation helpers for emitting metrics to Prometheus."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

from telemetry.contracts import MetricSnapshot

if TYPE_CHECKING:
    from core.bus import BusProto


logger = logging.getLogger(__name__)


class MetricsEmitter:
    """Helper for emitting metrics to the telemetry bus.

    Handles environment-based gating and graceful degradation.
    """

    def __init__(self, bus: BusProto) -> None:
        """Initialize metrics emitter.

        Args:
            bus: Event bus instance
        """
        self.bus = bus
        self._enabled = os.getenv("NJORD_ENABLE_METRICS") == "1"
        self._metrics_topic = "telemetry.metrics"

    def is_enabled(self) -> bool:
        """Check if metrics emission is enabled."""
        return self._enabled

    async def emit_counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """Emit a counter metric.

        Args:
            name: Metric name
            value: Counter increment value
            labels: Metric labels
        """
        if not self._enabled:
            return

        try:
            snapshot = MetricSnapshot(
                name=name,
                value=value,
                timestamp_ns=int(time.time() * 1e9),
                labels=labels or {},
                metric_type="counter",
            )
            await self.bus.publish_json(self._metrics_topic, snapshot.to_dict())
        except Exception:
            # Graceful degradation: log locally but don't crash
            logger.debug(
                "telemetry.emit_failed",
                extra={"metric_name": name, "metric_type": "counter"},
                exc_info=True,
            )

    async def emit_gauge(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Emit a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            labels: Metric labels
        """
        if not self._enabled:
            return

        try:
            snapshot = MetricSnapshot(
                name=name,
                value=value,
                timestamp_ns=int(time.time() * 1e9),
                labels=labels or {},
                metric_type="gauge",
            )
            await self.bus.publish_json(self._metrics_topic, snapshot.to_dict())
        except Exception:
            logger.debug(
                "telemetry.emit_failed",
                extra={"metric_name": name, "metric_type": "gauge"},
                exc_info=True,
            )

    async def emit_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Emit a histogram observation.

        Args:
            name: Metric name
            value: Observation value
            labels: Metric labels
        """
        if not self._enabled:
            return

        try:
            snapshot = MetricSnapshot(
                name=name,
                value=value,
                timestamp_ns=int(time.time() * 1e9),
                labels=labels or {},
                metric_type="histogram",
            )
            await self.bus.publish_json(self._metrics_topic, snapshot.to_dict())
        except Exception:
            logger.debug(
                "telemetry.emit_failed",
                extra={"metric_name": name, "metric_type": "histogram"},
                exc_info=True,
            )
