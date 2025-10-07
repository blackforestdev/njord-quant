"""Telemetry contracts for metrics collection and reporting.

This module defines contracts for Prometheus-compatible metrics collection,
strategy performance tracking, and system health monitoring.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar, Literal

logger = logging.getLogger(__name__)

MetricType = Literal["counter", "gauge", "histogram", "summary"]

_LabelKey = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MetricSnapshot:
    """Single metric measurement.

    Represents a point-in-time measurement of a metric with labels.
    Follows Prometheus metric conventions.

    Attributes:
        name: Metric name (snake_case, e.g., "njord_orders_total")
        value: Metric value
        timestamp_ns: Measurement timestamp (nanoseconds since epoch)
        labels: Label key-value pairs (e.g., {"strategy_id": "twap_v1"})
        metric_type: Prometheus metric type

    Raises:
        ValueError: If name is empty, labels dict has >20 keys, or timestamp is negative
    """

    name: str
    value: float
    timestamp_ns: int
    labels: Mapping[str, str] = field(default_factory=dict)
    metric_type: MetricType = "gauge"

    _LABEL_CARDINALITY_WARNING_THRESHOLD: ClassVar[int] = 100
    _LABEL_CARDINALITY_MAX_TRACKED: ClassVar[int] = 128
    _label_combinations: ClassVar[dict[str, OrderedDict[_LabelKey, None]]] = {}
    _warned_metrics: ClassVar[set[str]] = set()

    def __post_init__(self) -> None:
        """Validate metric snapshot configuration."""
        self._validate_metric_name()
        self._validate_timestamp()
        labels_copy = dict(self.labels)
        self._validate_label_cardinality(labels_copy)
        object.__setattr__(self, "labels", MappingProxyType(labels_copy))
        self._validate_metric_type()
        self._track_label_combination()

    def _validate_metric_name(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")

    def _validate_timestamp(self) -> None:
        if self.timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be >= 0, got {self.timestamp_ns}")

    def _validate_label_cardinality(self, labels: dict[str, str]) -> None:
        if len(labels) > 20:
            raise ValueError(
                f"labels must have <= 20 keys (got {len(labels)}). "
                "High-cardinality labels can cause performance issues."
            )

    def _validate_metric_type(self) -> None:
        if self.metric_type not in ("counter", "gauge", "histogram", "summary"):
            raise ValueError(
                "metric_type must be one of {'counter', 'gauge', 'histogram', 'summary'} "
                f"(got {self.metric_type!r})"
            )

    def _track_label_combination(self) -> None:
        if not self.labels:
            return
        label_key: _LabelKey = tuple(sorted(self.labels.items()))
        combinations = self._label_combinations.setdefault(self.name, OrderedDict())

        if label_key in combinations:
            combinations.move_to_end(label_key)
        else:
            combinations[label_key] = None
            if len(combinations) > self._LABEL_CARDINALITY_MAX_TRACKED:
                combinations.popitem(last=False)

        unique_count = len(combinations)
        threshold = self._LABEL_CARDINALITY_WARNING_THRESHOLD
        if unique_count > threshold and self.name not in self._warned_metrics:
            logger.warning(
                "telemetry.metric_cardinality_high",
                extra={
                    "metric_name": self.name,
                    "unique_combinations": unique_count,
                    "threshold": threshold,
                },
            )
            self._warned_metrics.add(self.name)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of MetricSnapshot
        """
        return {
            "name": self.name,
            "value": self.value,
            "timestamp_ns": self.timestamp_ns,
            "labels": dict(self.labels),
            "metric_type": self.metric_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricSnapshot:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with metric snapshot data

        Returns:
            MetricSnapshot instance
        """
        return cls(
            name=data["name"],
            value=data["value"],
            timestamp_ns=data["timestamp_ns"],
            labels=dict(data.get("labels", {})),
            metric_type=data.get("metric_type", "gauge"),
        )


@dataclass(frozen=True)
class StrategyMetrics:
    """Strategy-level performance metrics.

    Aggregated metrics for a single strategy instance.

    Attributes:
        strategy_id: Strategy identifier
        timestamp_ns: Measurement timestamp (nanoseconds since epoch)
        active_positions: Number of active positions
        total_pnl: Total profit/loss (USD)
        daily_pnl: Daily profit/loss (USD)
        win_rate: Win rate (0.0-1.0)
        sharpe_ratio: Sharpe ratio
        max_drawdown_pct: Maximum drawdown percentage (0.0-100.0)
        orders_sent: Total orders sent
        orders_filled: Total orders filled
        orders_rejected: Total orders rejected

    Raises:
        ValueError: If win_rate not in [0, 1], max_drawdown_pct not in [0, 100],
                   or counts are negative
    """

    strategy_id: str
    timestamp_ns: int
    active_positions: int
    total_pnl: float
    daily_pnl: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown_pct: float
    orders_sent: int
    orders_filled: int
    orders_rejected: int

    def __post_init__(self) -> None:
        """Validate strategy metrics."""
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be >= 0, got {self.timestamp_ns}")
        if not 0.0 <= self.win_rate <= 1.0:
            raise ValueError(f"win_rate must be in [0, 1], got {self.win_rate}")
        if not 0.0 <= self.max_drawdown_pct <= 100.0:
            raise ValueError(f"max_drawdown_pct must be in [0, 100], got {self.max_drawdown_pct}")
        if self.active_positions < 0:
            raise ValueError(f"active_positions must be >= 0, got {self.active_positions}")
        if self.orders_sent < 0:
            raise ValueError(f"orders_sent must be >= 0, got {self.orders_sent}")
        if self.orders_filled < 0:
            raise ValueError(f"orders_filled must be >= 0, got {self.orders_filled}")
        if self.orders_rejected < 0:
            raise ValueError(f"orders_rejected must be >= 0, got {self.orders_rejected}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of StrategyMetrics
        """
        return {
            "strategy_id": self.strategy_id,
            "timestamp_ns": self.timestamp_ns,
            "active_positions": self.active_positions,
            "total_pnl": self.total_pnl,
            "daily_pnl": self.daily_pnl,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "orders_sent": self.orders_sent,
            "orders_filled": self.orders_filled,
            "orders_rejected": self.orders_rejected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyMetrics:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with strategy metrics data

        Returns:
            StrategyMetrics instance
        """
        return cls(
            strategy_id=data["strategy_id"],
            timestamp_ns=data["timestamp_ns"],
            active_positions=data["active_positions"],
            total_pnl=data["total_pnl"],
            daily_pnl=data["daily_pnl"],
            win_rate=data["win_rate"],
            sharpe_ratio=data["sharpe_ratio"],
            max_drawdown_pct=data["max_drawdown_pct"],
            orders_sent=data["orders_sent"],
            orders_filled=data["orders_filled"],
            orders_rejected=data["orders_rejected"],
        )


@dataclass(frozen=True)
class SystemMetrics:
    """System-level health metrics.

    Aggregated metrics for the entire trading system.

    Attributes:
        timestamp_ns: Measurement timestamp (nanoseconds since epoch)
        bus_messages_sent: Total bus messages sent
        bus_messages_received: Total bus messages received
        journal_writes: Total journal writes
        journal_bytes: Total journal bytes written
        active_subscriptions: Number of active bus subscriptions
        event_loop_lag_ms: Event loop lag in milliseconds
        memory_usage_mb: Memory usage in megabytes

    Raises:
        ValueError: If counts are negative or event_loop_lag_ms/memory_usage_mb < 0
    """

    timestamp_ns: int
    bus_messages_sent: int
    bus_messages_received: int
    journal_writes: int
    journal_bytes: int
    active_subscriptions: int
    event_loop_lag_ms: float
    memory_usage_mb: float

    def __post_init__(self) -> None:
        """Validate system metrics."""
        if self.timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be >= 0, got {self.timestamp_ns}")
        if self.bus_messages_sent < 0:
            raise ValueError(f"bus_messages_sent must be >= 0, got {self.bus_messages_sent}")
        if self.bus_messages_received < 0:
            raise ValueError(
                f"bus_messages_received must be >= 0, got {self.bus_messages_received}"
            )
        if self.journal_writes < 0:
            raise ValueError(f"journal_writes must be >= 0, got {self.journal_writes}")
        if self.journal_bytes < 0:
            raise ValueError(f"journal_bytes must be >= 0, got {self.journal_bytes}")
        if self.active_subscriptions < 0:
            raise ValueError(f"active_subscriptions must be >= 0, got {self.active_subscriptions}")
        if self.event_loop_lag_ms < 0:
            raise ValueError(f"event_loop_lag_ms must be >= 0, got {self.event_loop_lag_ms}")
        if self.memory_usage_mb < 0:
            raise ValueError(f"memory_usage_mb must be >= 0, got {self.memory_usage_mb}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of SystemMetrics
        """
        return {
            "timestamp_ns": self.timestamp_ns,
            "bus_messages_sent": self.bus_messages_sent,
            "bus_messages_received": self.bus_messages_received,
            "journal_writes": self.journal_writes,
            "journal_bytes": self.journal_bytes,
            "active_subscriptions": self.active_subscriptions,
            "event_loop_lag_ms": self.event_loop_lag_ms,
            "memory_usage_mb": self.memory_usage_mb,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemMetrics:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with system metrics data

        Returns:
            SystemMetrics instance
        """
        return cls(
            timestamp_ns=data["timestamp_ns"],
            bus_messages_sent=data["bus_messages_sent"],
            bus_messages_received=data["bus_messages_received"],
            journal_writes=data["journal_writes"],
            journal_bytes=data["journal_bytes"],
            active_subscriptions=data["active_subscriptions"],
            event_loop_lag_ms=data["event_loop_lag_ms"],
            memory_usage_mb=data["memory_usage_mb"],
        )
