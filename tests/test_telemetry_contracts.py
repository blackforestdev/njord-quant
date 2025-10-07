"""Tests for telemetry contracts."""

from __future__ import annotations

import time
from typing import Any

import pytest

from telemetry.contracts import MetricSnapshot, StrategyMetrics, SystemMetrics


class TestMetricSnapshot:
    """Tests for MetricSnapshot contract."""

    def test_creates_valid_metric_snapshot(self) -> None:
        """Test creating valid MetricSnapshot."""
        ts = int(time.time() * 1e9)
        snapshot = MetricSnapshot(
            name="njord_orders_total",
            value=42.0,
            timestamp_ns=ts,
            labels={"strategy_id": "twap_v1", "symbol": "BTC/USDT"},
            metric_type="counter",
        )

        assert snapshot.name == "njord_orders_total"
        assert snapshot.value == 42.0
        assert snapshot.timestamp_ns == ts
        assert snapshot.labels == {"strategy_id": "twap_v1", "symbol": "BTC/USDT"}
        assert snapshot.metric_type == "counter"

    def test_defaults_to_gauge_with_empty_labels(self) -> None:
        """Test MetricSnapshot defaults (gauge type, empty labels)."""
        snapshot = MetricSnapshot(
            name="test_metric",
            value=1.0,
            timestamp_ns=0,
        )

        assert snapshot.metric_type == "gauge"
        assert snapshot.labels == {}

    def test_supports_all_metric_types(self) -> None:
        """Test MetricSnapshot supports all Prometheus metric types."""
        ts = int(time.time() * 1e9)
        for metric_type in ["counter", "gauge", "histogram", "summary"]:
            snapshot = MetricSnapshot(
                name="test_metric",
                value=1.0,
                timestamp_ns=ts,
                metric_type=metric_type,  # type: ignore[arg-type]
            )
            assert snapshot.metric_type == metric_type

    def test_rejects_unknown_metric_type(self) -> None:
        """Test MetricSnapshot rejects unsupported metric types."""
        with pytest.raises(ValueError, match="metric_type must be one of"):
            MetricSnapshot(
                name="test_metric",
                value=1.0,
                timestamp_ns=0,
                metric_type="invalid",  # type: ignore[arg-type]
            )

    def test_rejects_empty_name(self) -> None:
        """Test MetricSnapshot rejects empty name."""
        with pytest.raises(ValueError, match="name must not be empty"):
            MetricSnapshot(
                name="",
                value=1.0,
                timestamp_ns=0,
            )

    def test_rejects_negative_timestamp(self) -> None:
        """Test MetricSnapshot rejects negative timestamp."""
        with pytest.raises(ValueError, match="timestamp_ns must be >= 0"):
            MetricSnapshot(
                name="test_metric",
                value=1.0,
                timestamp_ns=-1,
            )

    def test_rejects_high_cardinality_labels(self) -> None:
        """Test MetricSnapshot rejects >20 label keys."""
        labels = {f"label_{i}": f"value_{i}" for i in range(21)}
        with pytest.raises(ValueError, match="labels must have <= 20 keys"):
            MetricSnapshot(
                name="test_metric",
                value=1.0,
                timestamp_ns=0,
                labels=labels,
            )

    def test_allows_exactly_20_label_keys(self) -> None:
        """Test MetricSnapshot allows exactly 20 label keys."""
        labels = {f"label_{i}": f"value_{i}" for i in range(20)}
        snapshot = MetricSnapshot(
            name="test_metric",
            value=1.0,
            timestamp_ns=0,
            labels=labels,
        )
        assert len(snapshot.labels) == 20

    def test_warns_on_high_cardinality_label_combinations(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test MetricSnapshot warns when label combinations exceed threshold."""

        MetricSnapshot._label_combinations.clear()
        MetricSnapshot._warned_metrics.clear()

        monkeypatch.setattr(MetricSnapshot, "_LABEL_CARDINALITY_WARNING_THRESHOLD", 2)
        monkeypatch.setattr(MetricSnapshot, "_LABEL_CARDINALITY_MAX_TRACKED", 5)

        caplog.set_level("WARNING")

        ts = int(time.time() * 1e9)
        for offset in range(4):
            MetricSnapshot(
                name="njord_orders_total",
                value=float(offset),
                timestamp_ns=ts + offset,
                labels={"strategy_id": f"strategy_{offset}"},
            )

        warning_messages = [record.message for record in caplog.records]
        assert "telemetry.metric_cardinality_high" in warning_messages
        assert warning_messages.count("telemetry.metric_cardinality_high") == 1

    def test_serializes_to_dict(self) -> None:
        """Test MetricSnapshot.to_dict()."""
        ts = int(time.time() * 1e9)
        snapshot = MetricSnapshot(
            name="njord_fills_total",
            value=10.0,
            timestamp_ns=ts,
            labels={"symbol": "ETH/USDT"},
            metric_type="counter",
        )

        data = snapshot.to_dict()

        assert data == {
            "name": "njord_fills_total",
            "value": 10.0,
            "timestamp_ns": ts,
            "labels": {"symbol": "ETH/USDT"},
            "metric_type": "counter",
        }

    def test_to_dict_copies_labels(self) -> None:
        """Test to_dict() returns copy of labels dict."""
        snapshot = MetricSnapshot(
            name="test",
            value=1.0,
            timestamp_ns=0,
            labels={"key": "value"},
        )

        data = snapshot.to_dict()
        data["labels"]["new_key"] = "new_value"

        # Original snapshot labels should be unchanged
        assert "new_key" not in snapshot.labels

    def test_labels_mapping_is_immutable(self) -> None:
        """Test MetricSnapshot labels mapping cannot be mutated."""
        snapshot = MetricSnapshot(
            name="immutable_test",
            value=1.0,
            timestamp_ns=0,
            labels={"key": "value"},
        )

        with pytest.raises(TypeError):
            snapshot.labels["new_key"] = "new_value"  # type: ignore[index]

    def test_deserializes_from_dict(self) -> None:
        """Test MetricSnapshot.from_dict()."""
        ts = int(time.time() * 1e9)
        data: dict[str, Any] = {
            "name": "njord_pnl_usd",
            "value": 1234.56,
            "timestamp_ns": ts,
            "labels": {"strategy_id": "momentum_v2"},
            "metric_type": "gauge",
        }

        snapshot = MetricSnapshot.from_dict(data)

        # Mutating original data should not affect the snapshot
        data["labels"]["strategy_id"] = "changed"

        assert snapshot.name == "njord_pnl_usd"
        assert snapshot.value == 1234.56
        assert snapshot.timestamp_ns == ts
        assert snapshot.labels == {"strategy_id": "momentum_v2"}
        assert snapshot.metric_type == "gauge"
        with pytest.raises(TypeError):
            snapshot.labels["new"] = "value"  # type: ignore[index]

    def test_from_dict_uses_defaults(self) -> None:
        """Test from_dict() applies defaults for optional fields."""
        data = {
            "name": "test_metric",
            "value": 1.0,
            "timestamp_ns": 0,
        }

        snapshot = MetricSnapshot.from_dict(data)

        assert snapshot.labels == {}
        assert snapshot.metric_type == "gauge"

    def test_round_trip_serialization(self) -> None:
        """Test MetricSnapshot survives to_dict/from_dict round-trip."""
        ts = int(time.time() * 1e9)
        original = MetricSnapshot(
            name="njord_latency_ms",
            value=23.45,
            timestamp_ns=ts,
            labels={"venue": "binance", "symbol": "BTC/USDT"},
            metric_type="histogram",
        )

        data = original.to_dict()
        restored = MetricSnapshot.from_dict(data)

        assert restored == original


class TestStrategyMetrics:
    """Tests for StrategyMetrics contract."""

    def test_creates_valid_strategy_metrics(self) -> None:
        """Test creating valid StrategyMetrics."""
        ts = int(time.time() * 1e9)
        metrics = StrategyMetrics(
            strategy_id="momentum_v1",
            timestamp_ns=ts,
            active_positions=3,
            total_pnl=1234.56,
            daily_pnl=234.56,
            win_rate=0.65,
            sharpe_ratio=1.8,
            max_drawdown_pct=12.5,
            orders_sent=100,
            orders_filled=95,
            orders_rejected=5,
        )

        assert metrics.strategy_id == "momentum_v1"
        assert metrics.timestamp_ns == ts
        assert metrics.active_positions == 3
        assert metrics.total_pnl == 1234.56
        assert metrics.daily_pnl == 234.56
        assert metrics.win_rate == 0.65
        assert metrics.sharpe_ratio == 1.8
        assert metrics.max_drawdown_pct == 12.5
        assert metrics.orders_sent == 100
        assert metrics.orders_filled == 95
        assert metrics.orders_rejected == 5

    def test_rejects_empty_strategy_id(self) -> None:
        """Test StrategyMetrics rejects empty strategy_id."""
        with pytest.raises(ValueError, match="strategy_id must not be empty"):
            StrategyMetrics(
                strategy_id="",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.0,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

    def test_rejects_negative_timestamp(self) -> None:
        """Test StrategyMetrics rejects negative timestamp."""
        with pytest.raises(ValueError, match="timestamp_ns must be >= 0"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=-1,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.0,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

    def test_rejects_win_rate_out_of_range(self) -> None:
        """Test StrategyMetrics rejects win_rate outside [0, 1]."""
        # Above 1.0
        with pytest.raises(ValueError, match="win_rate must be in \\[0, 1\\]"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=1.1,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

        # Below 0.0
        with pytest.raises(ValueError, match="win_rate must be in \\[0, 1\\]"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=-0.1,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

    def test_rejects_max_drawdown_out_of_range(self) -> None:
        """Test StrategyMetrics rejects max_drawdown_pct outside [0, 100]."""
        # Above 100
        with pytest.raises(ValueError, match="max_drawdown_pct must be in \\[0, 100\\]"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.5,
                sharpe_ratio=0.0,
                max_drawdown_pct=101.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

        # Below 0
        with pytest.raises(ValueError, match="max_drawdown_pct must be in \\[0, 100\\]"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.5,
                sharpe_ratio=0.0,
                max_drawdown_pct=-1.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

    def test_rejects_negative_counts(self) -> None:
        """Test StrategyMetrics rejects negative count fields."""
        # Negative active_positions
        with pytest.raises(ValueError, match="active_positions must be >= 0"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=-1,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.5,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=0,
            )

        # Negative orders_sent
        with pytest.raises(ValueError, match="orders_sent must be >= 0"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.5,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=-1,
                orders_filled=0,
                orders_rejected=0,
            )

        # Negative orders_filled
        with pytest.raises(ValueError, match="orders_filled must be >= 0"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.5,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=-1,
                orders_rejected=0,
            )

        # Negative orders_rejected
        with pytest.raises(ValueError, match="orders_rejected must be >= 0"):
            StrategyMetrics(
                strategy_id="test",
                timestamp_ns=0,
                active_positions=0,
                total_pnl=0.0,
                daily_pnl=0.0,
                win_rate=0.5,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                orders_sent=0,
                orders_filled=0,
                orders_rejected=-1,
            )

    def test_serializes_to_dict(self) -> None:
        """Test StrategyMetrics.to_dict()."""
        ts = int(time.time() * 1e9)
        metrics = StrategyMetrics(
            strategy_id="twap_v2",
            timestamp_ns=ts,
            active_positions=2,
            total_pnl=500.0,
            daily_pnl=50.0,
            win_rate=0.7,
            sharpe_ratio=2.0,
            max_drawdown_pct=8.5,
            orders_sent=50,
            orders_filled=48,
            orders_rejected=2,
        )

        data = metrics.to_dict()

        assert data == {
            "strategy_id": "twap_v2",
            "timestamp_ns": ts,
            "active_positions": 2,
            "total_pnl": 500.0,
            "daily_pnl": 50.0,
            "win_rate": 0.7,
            "sharpe_ratio": 2.0,
            "max_drawdown_pct": 8.5,
            "orders_sent": 50,
            "orders_filled": 48,
            "orders_rejected": 2,
        }

    def test_deserializes_from_dict(self) -> None:
        """Test StrategyMetrics.from_dict()."""
        ts = int(time.time() * 1e9)
        data = {
            "strategy_id": "iceberg_v1",
            "timestamp_ns": ts,
            "active_positions": 1,
            "total_pnl": 1000.0,
            "daily_pnl": 100.0,
            "win_rate": 0.8,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 5.0,
            "orders_sent": 200,
            "orders_filled": 190,
            "orders_rejected": 10,
        }

        metrics = StrategyMetrics.from_dict(data)

        assert metrics.strategy_id == "iceberg_v1"
        assert metrics.timestamp_ns == ts
        assert metrics.active_positions == 1
        assert metrics.total_pnl == 1000.0
        assert metrics.daily_pnl == 100.0
        assert metrics.win_rate == 0.8
        assert metrics.sharpe_ratio == 1.5
        assert metrics.max_drawdown_pct == 5.0
        assert metrics.orders_sent == 200
        assert metrics.orders_filled == 190
        assert metrics.orders_rejected == 10

    def test_round_trip_serialization(self) -> None:
        """Test StrategyMetrics survives to_dict/from_dict round-trip."""
        ts = int(time.time() * 1e9)
        original = StrategyMetrics(
            strategy_id="pov_v3",
            timestamp_ns=ts,
            active_positions=5,
            total_pnl=-200.0,
            daily_pnl=-50.0,
            win_rate=0.45,
            sharpe_ratio=-0.5,
            max_drawdown_pct=25.0,
            orders_sent=300,
            orders_filled=280,
            orders_rejected=20,
        )

        data = original.to_dict()
        restored = StrategyMetrics.from_dict(data)

        assert restored == original


class TestSystemMetrics:
    """Tests for SystemMetrics contract."""

    def test_creates_valid_system_metrics(self) -> None:
        """Test creating valid SystemMetrics."""
        ts = int(time.time() * 1e9)
        metrics = SystemMetrics(
            timestamp_ns=ts,
            bus_messages_sent=1000,
            bus_messages_received=980,
            journal_writes=500,
            journal_bytes=1024000,
            active_subscriptions=15,
            event_loop_lag_ms=2.5,
            memory_usage_mb=256.5,
        )

        assert metrics.timestamp_ns == ts
        assert metrics.bus_messages_sent == 1000
        assert metrics.bus_messages_received == 980
        assert metrics.journal_writes == 500
        assert metrics.journal_bytes == 1024000
        assert metrics.active_subscriptions == 15
        assert metrics.event_loop_lag_ms == 2.5
        assert metrics.memory_usage_mb == 256.5

    def test_rejects_negative_timestamp(self) -> None:
        """Test SystemMetrics rejects negative timestamp."""
        with pytest.raises(ValueError, match="timestamp_ns must be >= 0"):
            SystemMetrics(
                timestamp_ns=-1,
                bus_messages_sent=0,
                bus_messages_received=0,
                journal_writes=0,
                journal_bytes=0,
                active_subscriptions=0,
                event_loop_lag_ms=0.0,
                memory_usage_mb=0.0,
            )

    def test_rejects_negative_counts(self) -> None:
        """Test SystemMetrics rejects negative count fields."""
        # Negative bus_messages_sent
        with pytest.raises(ValueError, match="bus_messages_sent must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=-1,
                bus_messages_received=0,
                journal_writes=0,
                journal_bytes=0,
                active_subscriptions=0,
                event_loop_lag_ms=0.0,
                memory_usage_mb=0.0,
            )

        # Negative bus_messages_received
        with pytest.raises(ValueError, match="bus_messages_received must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=0,
                bus_messages_received=-1,
                journal_writes=0,
                journal_bytes=0,
                active_subscriptions=0,
                event_loop_lag_ms=0.0,
                memory_usage_mb=0.0,
            )

        # Negative journal_writes
        with pytest.raises(ValueError, match="journal_writes must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=0,
                bus_messages_received=0,
                journal_writes=-1,
                journal_bytes=0,
                active_subscriptions=0,
                event_loop_lag_ms=0.0,
                memory_usage_mb=0.0,
            )

        # Negative journal_bytes
        with pytest.raises(ValueError, match="journal_bytes must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=0,
                bus_messages_received=0,
                journal_writes=0,
                journal_bytes=-1,
                active_subscriptions=0,
                event_loop_lag_ms=0.0,
                memory_usage_mb=0.0,
            )

        # Negative active_subscriptions
        with pytest.raises(ValueError, match="active_subscriptions must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=0,
                bus_messages_received=0,
                journal_writes=0,
                journal_bytes=0,
                active_subscriptions=-1,
                event_loop_lag_ms=0.0,
                memory_usage_mb=0.0,
            )

    def test_rejects_negative_lag_and_memory(self) -> None:
        """Test SystemMetrics rejects negative event_loop_lag_ms and memory_usage_mb."""
        # Negative event_loop_lag_ms
        with pytest.raises(ValueError, match="event_loop_lag_ms must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=0,
                bus_messages_received=0,
                journal_writes=0,
                journal_bytes=0,
                active_subscriptions=0,
                event_loop_lag_ms=-1.0,
                memory_usage_mb=0.0,
            )

        # Negative memory_usage_mb
        with pytest.raises(ValueError, match="memory_usage_mb must be >= 0"):
            SystemMetrics(
                timestamp_ns=0,
                bus_messages_sent=0,
                bus_messages_received=0,
                journal_writes=0,
                journal_bytes=0,
                active_subscriptions=0,
                event_loop_lag_ms=0.0,
                memory_usage_mb=-1.0,
            )

    def test_serializes_to_dict(self) -> None:
        """Test SystemMetrics.to_dict()."""
        ts = int(time.time() * 1e9)
        metrics = SystemMetrics(
            timestamp_ns=ts,
            bus_messages_sent=500,
            bus_messages_received=490,
            journal_writes=250,
            journal_bytes=512000,
            active_subscriptions=10,
            event_loop_lag_ms=1.5,
            memory_usage_mb=128.0,
        )

        data = metrics.to_dict()

        assert data == {
            "timestamp_ns": ts,
            "bus_messages_sent": 500,
            "bus_messages_received": 490,
            "journal_writes": 250,
            "journal_bytes": 512000,
            "active_subscriptions": 10,
            "event_loop_lag_ms": 1.5,
            "memory_usage_mb": 128.0,
        }

    def test_deserializes_from_dict(self) -> None:
        """Test SystemMetrics.from_dict()."""
        ts = int(time.time() * 1e9)
        data = {
            "timestamp_ns": ts,
            "bus_messages_sent": 2000,
            "bus_messages_received": 1950,
            "journal_writes": 1000,
            "journal_bytes": 2048000,
            "active_subscriptions": 20,
            "event_loop_lag_ms": 5.0,
            "memory_usage_mb": 512.0,
        }

        metrics = SystemMetrics.from_dict(data)

        assert metrics.timestamp_ns == ts
        assert metrics.bus_messages_sent == 2000
        assert metrics.bus_messages_received == 1950
        assert metrics.journal_writes == 1000
        assert metrics.journal_bytes == 2048000
        assert metrics.active_subscriptions == 20
        assert metrics.event_loop_lag_ms == 5.0
        assert metrics.memory_usage_mb == 512.0

    def test_round_trip_serialization(self) -> None:
        """Test SystemMetrics survives to_dict/from_dict round-trip."""
        ts = int(time.time() * 1e9)
        original = SystemMetrics(
            timestamp_ns=ts,
            bus_messages_sent=10000,
            bus_messages_received=9950,
            journal_writes=5000,
            journal_bytes=10240000,
            active_subscriptions=50,
            event_loop_lag_ms=10.5,
            memory_usage_mb=1024.5,
        )

        data = original.to_dict()
        restored = SystemMetrics.from_dict(data)

        assert restored == original
