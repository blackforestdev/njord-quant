"""Metric registry for storing and managing Prometheus-compatible metrics."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class Counter:
    """Prometheus counter metric (monotonically increasing).

    Counters can only increase or be reset to zero on restart.
    """

    def __init__(self, name: str, help_text: str, label_names: list[str] | None = None) -> None:
        """Initialize counter.

        Args:
            name: Metric name
            help_text: Help text for metric
            label_names: List of label names (optional)
        """
        self.name = name
        self.help_text = help_text
        self.label_names = label_names or []
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = asyncio.Lock()

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment counter.

        Args:
            amount: Amount to increment by (must be >= 0)
            labels: Label values

        Raises:
            ValueError: If amount < 0 or labels don't match label_names
        """
        if amount < 0:
            raise ValueError(f"Counter can only increase, got negative amount: {amount}")

        label_values = self._validate_and_extract_labels(labels)
        self._values[label_values] += amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get counter value for given labels.

        Args:
            labels: Label values

        Returns:
            Current counter value
        """
        label_values = self._validate_and_extract_labels(labels)
        return self._values[label_values]

    def _validate_and_extract_labels(self, labels: dict[str, str] | None) -> tuple[str, ...]:
        """Validate labels and extract values in correct order.

        Args:
            labels: Label dictionary

        Returns:
            Tuple of label values in order of label_names

        Raises:
            ValueError: If label keys don't match label_names
        """
        if not self.label_names:
            if labels:
                raise ValueError(f"Metric {self.name} has no labels, but labels were provided")
            return ()

        if not labels:
            raise ValueError(
                f"Metric {self.name} requires labels {self.label_names}, but none provided"
            )

        label_keys = set(labels.keys())
        expected_keys = set(self.label_names)
        if label_keys != expected_keys:
            raise ValueError(
                f"Label keys {label_keys} don't match expected {expected_keys} "
                f"for metric {self.name}"
            )

        return tuple(labels[name] for name in self.label_names)

    def collect(self) -> list[tuple[dict[str, str], float]]:
        """Collect all label combinations and their values.

        Returns:
            List of (labels_dict, value) tuples
        """
        results: list[tuple[dict[str, str], float]] = []
        for label_values, value in self._values.items():
            labels_dict = (
                dict(zip(self.label_names, label_values, strict=True)) if self.label_names else {}
            )
            results.append((labels_dict, value))
        return results


class Gauge:
    """Prometheus gauge metric (can go up and down)."""

    def __init__(self, name: str, help_text: str, label_names: list[str] | None = None) -> None:
        """Initialize gauge.

        Args:
            name: Metric name
            help_text: Help text for metric
            label_names: List of label names (optional)
        """
        self.name = name
        self.help_text = help_text
        self.label_names = label_names or []
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = asyncio.Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Set gauge to specific value.

        Args:
            value: Value to set
            labels: Label values
        """
        label_values = self._validate_and_extract_labels(labels)
        self._values[label_values] = value

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment gauge.

        Args:
            amount: Amount to increment by
            labels: Label values
        """
        label_values = self._validate_and_extract_labels(labels)
        self._values[label_values] += amount

    def dec(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Decrement gauge.

        Args:
            amount: Amount to decrement by
            labels: Label values
        """
        label_values = self._validate_and_extract_labels(labels)
        self._values[label_values] -= amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get gauge value for given labels.

        Args:
            labels: Label values

        Returns:
            Current gauge value
        """
        label_values = self._validate_and_extract_labels(labels)
        return self._values[label_values]

    def _validate_and_extract_labels(self, labels: dict[str, str] | None) -> tuple[str, ...]:
        """Validate labels and extract values in correct order."""
        if not self.label_names:
            if labels:
                raise ValueError(f"Metric {self.name} has no labels, but labels were provided")
            return ()

        if not labels:
            raise ValueError(
                f"Metric {self.name} requires labels {self.label_names}, but none provided"
            )

        label_keys = set(labels.keys())
        expected_keys = set(self.label_names)
        if label_keys != expected_keys:
            raise ValueError(
                f"Label keys {label_keys} don't match expected {expected_keys} "
                f"for metric {self.name}"
            )

        return tuple(labels[name] for name in self.label_names)

    def collect(self) -> list[tuple[dict[str, str], float]]:
        """Collect all label combinations and their values.

        Returns:
            List of (labels_dict, value) tuples
        """
        results: list[tuple[dict[str, str], float]] = []
        for label_values, value in self._values.items():
            labels_dict = (
                dict(zip(self.label_names, label_values, strict=True)) if self.label_names else {}
            )
            results.append((labels_dict, value))
        return results


class Histogram:
    """Prometheus histogram metric (samples observations into buckets)."""

    def __init__(
        self,
        name: str,
        help_text: str,
        buckets: list[float],
        label_names: list[str] | None = None,
    ) -> None:
        """Initialize histogram.

        Args:
            name: Metric name
            help_text: Help text for metric
            buckets: Bucket boundaries (must be sorted)
            label_names: List of label names (optional)

        Raises:
            ValueError: If buckets are not sorted or empty
        """
        self.name = name
        self.help_text = help_text
        self.label_names = label_names or []

        if not buckets:
            raise ValueError("buckets must not be empty")
        if buckets != sorted(buckets):
            raise ValueError(f"buckets must be sorted, got {buckets}")

        self.buckets = list(buckets)
        # Histogram state per label combination: {label_values: (bucket_counts, sum, count)}
        self._data: dict[tuple[str, ...], tuple[list[int], float, int]] = defaultdict(
            lambda: ([0] * len(self.buckets), 0.0, 0)
        )
        self._lock = asyncio.Lock()

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Observe a value (add to histogram).

        Args:
            value: Value to observe
            labels: Label values
        """
        label_values = self._validate_and_extract_labels(labels)
        bucket_counts, current_sum, current_count = self._data[label_values]

        # Update buckets
        new_bucket_counts = list(bucket_counts)
        for i, bucket_upper_bound in enumerate(self.buckets):
            if value <= bucket_upper_bound:
                new_bucket_counts[i] += 1

        # Update sum and count
        new_sum = current_sum + value
        new_count = current_count + 1

        self._data[label_values] = (new_bucket_counts, new_sum, new_count)

    def get(self, labels: dict[str, str] | None = None) -> dict[str, Any]:
        """Get histogram data for given labels.

        Args:
            labels: Label values

        Returns:
            Dictionary with bucket_counts, sum, count
        """
        label_values = self._validate_and_extract_labels(labels)
        bucket_counts, sum_val, count_val = self._data[label_values]
        return {"bucket_counts": list(bucket_counts), "sum": sum_val, "count": count_val}

    def _validate_and_extract_labels(self, labels: dict[str, str] | None) -> tuple[str, ...]:
        """Validate labels and extract values in correct order."""
        if not self.label_names:
            if labels:
                raise ValueError(f"Metric {self.name} has no labels, but labels were provided")
            return ()

        if not labels:
            raise ValueError(
                f"Metric {self.name} requires labels {self.label_names}, but none provided"
            )

        label_keys = set(labels.keys())
        expected_keys = set(self.label_names)
        if label_keys != expected_keys:
            raise ValueError(
                f"Label keys {label_keys} don't match expected {expected_keys} "
                f"for metric {self.name}"
            )

        return tuple(labels[name] for name in self.label_names)

    def collect(self) -> list[tuple[dict[str, str], list[int], float, int]]:
        """Collect all label combinations and their histogram data.

        Returns:
            List of (labels_dict, bucket_counts, sum, count) tuples
        """
        results: list[tuple[dict[str, str], list[int], float, int]] = []
        for label_values, (bucket_counts, sum_val, count_val) in self._data.items():
            labels_dict = (
                dict(zip(self.label_names, label_values, strict=True)) if self.label_names else {}
            )
            results.append((labels_dict, list(bucket_counts), sum_val, count_val))
        return results


class MetricRegistry:
    """Registry for storing and managing metrics."""

    def __init__(self) -> None:
        """Initialize metric registry."""
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = asyncio.Lock()

    async def register_counter(
        self, name: str, help_text: str, label_names: list[str] | None = None
    ) -> Counter:
        """Register a counter metric.

        Args:
            name: Metric name
            help_text: Help text
            label_names: Label names

        Returns:
            Counter instance

        Raises:
            ValueError: If metric with same name already registered
        """
        async with self._lock:
            if name in self._counters:
                raise ValueError(f"Counter {name} already registered")
            if name in self._gauges or name in self._histograms:
                raise ValueError(f"Metric {name} already registered as different type")

            counter = Counter(name, help_text, label_names)
            self._counters[name] = counter
            return counter

    async def register_gauge(
        self, name: str, help_text: str, label_names: list[str] | None = None
    ) -> Gauge:
        """Register a gauge metric.

        Args:
            name: Metric name
            help_text: Help text
            label_names: Label names

        Returns:
            Gauge instance

        Raises:
            ValueError: If metric with same name already registered
        """
        async with self._lock:
            if name in self._gauges:
                raise ValueError(f"Gauge {name} already registered")
            if name in self._counters or name in self._histograms:
                raise ValueError(f"Metric {name} already registered as different type")

            gauge = Gauge(name, help_text, label_names)
            self._gauges[name] = gauge
            return gauge

    async def register_histogram(
        self,
        name: str,
        help_text: str,
        buckets: list[float],
        label_names: list[str] | None = None,
    ) -> Histogram:
        """Register a histogram metric.

        Args:
            name: Metric name
            help_text: Help text
            buckets: Bucket boundaries
            label_names: Label names

        Returns:
            Histogram instance

        Raises:
            ValueError: If metric with same name already registered
        """
        async with self._lock:
            if name in self._histograms:
                raise ValueError(f"Histogram {name} already registered")
            if name in self._counters or name in self._gauges:
                raise ValueError(f"Metric {name} already registered as different type")

            histogram = Histogram(name, help_text, buckets, label_names)
            self._histograms[name] = histogram
            return histogram

    def get_counter(self, name: str) -> Counter | None:
        """Get counter by name."""
        return self._counters.get(name)

    def get_gauge(self, name: str) -> Gauge | None:
        """Get gauge by name."""
        return self._gauges.get(name)

    def get_histogram(self, name: str) -> Histogram | None:
        """Get histogram by name."""
        return self._histograms.get(name)

    def collect_all(self) -> dict[str, Any]:
        """Collect all metrics.

        Returns:
            Dictionary with counters, gauges, histograms
        """
        return {
            "counters": {name: counter for name, counter in self._counters.items()},
            "gauges": {name: gauge for name, gauge in self._gauges.items()},
            "histograms": {name: histogram for name, histogram in self._histograms.items()},
        }
