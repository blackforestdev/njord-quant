"""Tests for alert manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from telemetry.alerts import _DEDUP_WINDOW_NS, AlertManager, AlertRule, current_time_ns
from telemetry.contracts import Alert, MetricSnapshot
from tests.utils import InMemoryBus


class TestAlertRule:
    """Tests for AlertRule."""

    def test_alert_rule_from_dict(self) -> None:
        """Test loading alert rule from dictionary."""
        data = {
            "name": "high_drawdown",
            "metric": "njord_strategy_drawdown_pct",
            "condition": "> 10.0",
            "duration": 60,
            "labels": {"severity": "critical"},
            "annotations": {"summary": "Drawdown exceeded 10%"},
        }

        rule = AlertRule.from_dict(data)

        assert rule.name == "high_drawdown"
        assert rule.metric == "njord_strategy_drawdown_pct"
        assert rule.condition == "> 10.0"
        assert rule.duration == 60
        assert rule.labels == {"severity": "critical"}
        assert rule.annotations == {"summary": "Drawdown exceeded 10%"}

    def test_alert_rule_from_dict_defaults(self) -> None:
        """Test alert rule with default values."""
        data = {
            "name": "test_alert",
            "metric": "test_metric",
            "condition": "> 5.0",
        }

        rule = AlertRule.from_dict(data)

        assert rule.duration == 0
        assert rule.labels == {}
        assert rule.annotations == {}

    def test_alert_rule_from_dict_missing_name(self) -> None:
        """Test alert rule missing required name field."""
        data = {
            "metric": "test_metric",
            "condition": "> 5.0",
        }

        with pytest.raises(ValueError, match="missing required field: name"):
            AlertRule.from_dict(data)

    def test_alert_rule_from_dict_missing_metric(self) -> None:
        """Test alert rule missing required metric field."""
        data = {
            "name": "test_alert",
            "condition": "> 5.0",
        }

        with pytest.raises(ValueError, match="missing required field: metric"):
            AlertRule.from_dict(data)

    def test_alert_rule_from_dict_missing_condition(self) -> None:
        """Test alert rule missing required condition field."""
        data = {
            "name": "test_alert",
            "metric": "test_metric",
        }

        with pytest.raises(ValueError, match="missing required field: condition"):
            AlertRule.from_dict(data)


class TestAlertManager:
    """Tests for AlertManager."""

    def test_alert_manager_initialization(self) -> None:
        """Test alert manager initialization."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager.bus is bus
        assert manager.rules == []
        assert manager.active_alerts == {}
        assert manager.last_fired == {}

    def test_load_rules_from_yaml(self, tmp_path: Path) -> None:
        """Test loading alert rules from YAML file."""
        rules_file = tmp_path / "alerts.yaml"
        rules_file.write_text(
            """
alerts:
  - name: high_drawdown
    metric: njord_strategy_drawdown_pct
    condition: "> 10.0"
    duration: 60
    labels:
      severity: critical
    annotations:
      summary: "Drawdown exceeded"

  - name: event_loop_lag
    metric: njord_event_loop_lag_seconds
    condition: "> 0.1"
    duration: 30
    labels:
      severity: warning
"""
        )

        bus = InMemoryBus()
        manager = AlertManager(bus=bus, rules_path=rules_file)

        assert len(manager.rules) == 2
        assert manager.rules[0].name == "high_drawdown"
        assert manager.rules[0].metric == "njord_strategy_drawdown_pct"
        assert manager.rules[1].name == "event_loop_lag"
        assert manager.rules[1].metric == "njord_event_loop_lag_seconds"

    def test_load_rules_file_not_found(self) -> None:
        """Test loading rules from non-existent file."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        with pytest.raises(FileNotFoundError):
            manager.load_rules(Path("/nonexistent/alerts.yaml"))

    def test_load_rules_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML."""
        rules_file = tmp_path / "alerts.yaml"
        rules_file.write_text("- not a dict")

        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        with pytest.raises(ValueError, match="must contain a YAML dictionary"):
            manager.load_rules(rules_file)

    def test_load_rules_missing_alerts_key(self, tmp_path: Path) -> None:
        """Test loading YAML without alerts key."""
        rules_file = tmp_path / "alerts.yaml"
        rules_file.write_text("some_key: some_value")

        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        with pytest.raises(ValueError, match="must have 'alerts' key"):
            manager.load_rules(rules_file)

    def test_evaluate_condition_greater_than(self) -> None:
        """Test evaluating > condition."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager._evaluate_condition("> 10.0", 15.0) is True
        assert manager._evaluate_condition("> 10.0", 10.0) is False
        assert manager._evaluate_condition("> 10.0", 5.0) is False

    def test_evaluate_condition_greater_equal(self) -> None:
        """Test evaluating >= condition."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager._evaluate_condition(">= 10.0", 15.0) is True
        assert manager._evaluate_condition(">= 10.0", 10.0) is True
        assert manager._evaluate_condition(">= 10.0", 5.0) is False

    def test_evaluate_condition_less_than(self) -> None:
        """Test evaluating < condition."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager._evaluate_condition("< 10.0", 5.0) is True
        assert manager._evaluate_condition("< 10.0", 10.0) is False
        assert manager._evaluate_condition("< 10.0", 15.0) is False

    def test_evaluate_condition_less_equal(self) -> None:
        """Test evaluating <= condition."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager._evaluate_condition("<= 10.0", 5.0) is True
        assert manager._evaluate_condition("<= 10.0", 10.0) is True
        assert manager._evaluate_condition("<= 10.0", 15.0) is False

    def test_evaluate_condition_equals(self) -> None:
        """Test evaluating == condition."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager._evaluate_condition("== 10.0", 10.0) is True
        assert manager._evaluate_condition("== 10.0", 10.00001) is False

    def test_evaluate_condition_not_equals(self) -> None:
        """Test evaluating != condition."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        assert manager._evaluate_condition("!= 10.0", 5.0) is True
        assert manager._evaluate_condition("!= 10.0", 10.0) is False

    def test_evaluate_condition_invalid_format(self) -> None:
        """Test evaluating invalid condition format."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        # Invalid format
        assert manager._evaluate_condition("invalid", 10.0) is False

        # Unknown operator
        assert manager._evaluate_condition("?? 10.0", 10.0) is False

        # Invalid threshold
        assert manager._evaluate_condition("> abc", 10.0) is False

    @pytest.mark.asyncio
    async def test_evaluate_rules_no_match(self) -> None:
        """Test evaluating rules when metric doesn't match."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_test_metric",
                condition="> 10.0",
                duration=0,
                labels={},
                annotations={},
            )
        ]

        snapshot = MetricSnapshot(
            name="njord_other_metric",
            value=15.0,
            timestamp_ns=current_time_ns(),
        )

        alerts = await manager.evaluate_rules(snapshot)

        assert alerts == []
        assert len(manager.active_alerts) == 0

    @pytest.mark.asyncio
    async def test_evaluate_rules_immediate_fire(self) -> None:
        """Test evaluating rules with duration=0 (immediate fire)."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_test_metric",
                condition="> 10.0",
                duration=0,
                labels={"severity": "critical"},
                annotations={"summary": "Test alert"},
            )
        ]

        snapshot = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=current_time_ns(),
        )

        alerts = await manager.evaluate_rules(snapshot)

        assert len(alerts) == 1
        assert alerts[0].name == "test_alert"
        assert alerts[0].state == "firing"
        assert alerts[0].current_value == 15.0

    @pytest.mark.asyncio
    async def test_evaluate_rules_duration_not_met(self) -> None:
        """Test evaluating rules when duration not yet met."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_test_metric",
                condition="> 10.0",
                duration=60,  # 60 seconds
                labels={},
                annotations={},
            )
        ]

        now_ns = current_time_ns()
        snapshot = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=now_ns,
        )

        # First evaluation - should create pending alert
        alerts = await manager.evaluate_rules(snapshot)
        assert len(alerts) == 0  # Not fired yet
        assert len(manager.active_alerts) == 1

        # Check alert is pending
        alert_key = next(iter(manager.active_alerts.keys()))
        assert manager.active_alerts[alert_key].state == "pending"

    @pytest.mark.asyncio
    async def test_evaluate_rules_duration_met(self) -> None:
        """Test evaluating rules when duration requirement is met."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_test_metric",
                condition="> 10.0",
                duration=60,  # 60 seconds
                labels={},
                annotations={},
            )
        ]

        now_ns = current_time_ns()

        # First evaluation - creates pending alert
        snapshot1 = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=now_ns,
        )
        alerts = await manager.evaluate_rules(snapshot1)
        assert len(alerts) == 0

        # Second evaluation - 61 seconds later, should fire
        snapshot2 = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=now_ns + 61_000_000_000,  # +61 seconds
        )
        alerts = await manager.evaluate_rules(snapshot2)
        assert len(alerts) == 1
        assert alerts[0].state == "firing"

    @pytest.mark.asyncio
    async def test_evaluate_rules_auto_resolve(self) -> None:
        """Test alert auto-resolves when condition clears."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_test_metric",
                condition="> 10.0",
                duration=0,
                labels={},
                annotations={},
            )
        ]

        now_ns = current_time_ns()

        # Fire alert
        snapshot1 = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=now_ns,
        )
        alerts = await manager.evaluate_rules(snapshot1)
        assert len(alerts) == 1
        assert len(manager.active_alerts) == 1

        # Condition clears - should auto-resolve
        snapshot2 = MetricSnapshot(
            name="njord_test_metric",
            value=5.0,
            timestamp_ns=now_ns + 1_000_000_000,
        )
        alerts = await manager.evaluate_rules(snapshot2)
        assert len(alerts) == 0
        assert len(manager.active_alerts) == 0  # Resolved alerts removed

    @pytest.mark.asyncio
    async def test_fire_alert_publishes_to_bus(self) -> None:
        """Test fire_alert publishes to telemetry.alerts topic."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        alert = Alert(
            name="test_alert",
            metric_name="njord_test_metric",
            condition="> 10.0",
            current_value=15.0,
            timestamp_ns=current_time_ns(),
            labels={"severity": "critical"},
            annotations={"summary": "Test alert"},
            state="firing",
        )

        await manager.fire_alert(alert)

        assert "telemetry.alerts" in bus.published
        assert len(bus.published["telemetry.alerts"]) == 1

        published_alert = bus.published["telemetry.alerts"][0]
        assert published_alert["name"] == "test_alert"
        assert published_alert["state"] == "firing"

    @pytest.mark.asyncio
    async def test_deduplicate_alert_within_window(self) -> None:
        """Test deduplication prevents firing same alert within window."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        now_ns = current_time_ns()
        alert = Alert(
            name="test_alert",
            metric_name="njord_test_metric",
            condition="> 10.0",
            current_value=15.0,
            timestamp_ns=now_ns,
            state="firing",
        )

        # First fire - should succeed
        await manager.fire_alert(alert)
        assert len(bus.published["telemetry.alerts"]) == 1

        # Second fire within 5 min window - should be deduplicated
        alert2 = Alert(
            name="test_alert",
            metric_name="njord_test_metric",
            condition="> 10.0",
            current_value=20.0,
            timestamp_ns=now_ns + 60_000_000_000,  # +1 minute
            state="firing",
        )
        await manager.fire_alert(alert2)
        assert len(bus.published["telemetry.alerts"]) == 1  # Still 1

    @pytest.mark.asyncio
    async def test_deduplicate_alert_outside_window(self) -> None:
        """Test deduplication allows firing after window expires."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        now_ns = current_time_ns()
        alert = Alert(
            name="test_alert",
            metric_name="njord_test_metric",
            condition="> 10.0",
            current_value=15.0,
            timestamp_ns=now_ns,
            state="firing",
        )

        # First fire
        await manager.fire_alert(alert)
        assert len(bus.published["telemetry.alerts"]) == 1

        # Second fire after 5 min window - should succeed
        alert2 = Alert(
            name="test_alert",
            metric_name="njord_test_metric",
            condition="> 10.0",
            current_value=20.0,
            timestamp_ns=now_ns + _DEDUP_WINDOW_NS + 1,  # After window
            state="firing",
        )
        await manager.fire_alert(alert2)
        assert len(bus.published["telemetry.alerts"]) == 2  # Now 2

    @pytest.mark.asyncio
    async def test_process_metric_convenience_method(self) -> None:
        """Test process_metric convenience method."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_test_metric",
                condition="> 10.0",
                duration=0,
                labels={},
                annotations={},
            )
        ]

        snapshot = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=current_time_ns(),
        )

        await manager.process_metric(snapshot)

        # Should evaluate and fire alert
        assert "telemetry.alerts" in bus.published
        assert len(bus.published["telemetry.alerts"]) == 1

    @pytest.mark.asyncio
    async def test_alert_with_metric_labels(self) -> None:
        """Test alert includes metric labels."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_strategy_pnl_usd",
                condition="< -1000.0",
                duration=0,
                labels={"severity": "critical"},
                annotations={},
            )
        ]

        snapshot = MetricSnapshot(
            name="njord_strategy_pnl_usd",
            value=-1500.0,
            timestamp_ns=current_time_ns(),
            labels={"strategy_id": "alpha"},
        )

        alerts = await manager.evaluate_rules(snapshot)

        assert len(alerts) == 1
        assert "strategy_id" in alerts[0].labels
        assert alerts[0].labels["strategy_id"] == "alpha"
        assert alerts[0].labels["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_annotation_template_rendering(self) -> None:
        """Test annotation templates are rendered with metric labels."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="test_alert",
                metric="njord_strategy_pnl_usd",
                condition="< -1000.0",
                duration=0,
                labels={},
                annotations={"summary": "Strategy {{ $labels.strategy_id }} loss exceeded limit"},
            )
        ]

        snapshot = MetricSnapshot(
            name="njord_strategy_pnl_usd",
            value=-1500.0,
            timestamp_ns=current_time_ns(),
            labels={"strategy_id": "alpha"},
        )

        alerts = await manager.evaluate_rules(snapshot)

        assert len(alerts) == 1
        assert "summary" in alerts[0].annotations
        assert alerts[0].annotations["summary"] == "Strategy alpha loss exceeded limit"

    @pytest.mark.asyncio
    async def test_multiple_alerts_different_strategies(self) -> None:
        """Test multiple alerts fire for different strategy labels."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)
        manager.rules = [
            AlertRule(
                name="high_drawdown",
                metric="njord_strategy_drawdown_pct",
                condition="> 10.0",
                duration=0,
                labels={"severity": "critical"},
                annotations={},
            )
        ]

        # Alpha strategy exceeds threshold
        snapshot1 = MetricSnapshot(
            name="njord_strategy_drawdown_pct",
            value=12.0,
            timestamp_ns=current_time_ns(),
            labels={"strategy_id": "alpha"},
        )
        alerts1 = await manager.evaluate_rules(snapshot1)
        assert len(alerts1) == 1

        # Beta strategy also exceeds threshold
        snapshot2 = MetricSnapshot(
            name="njord_strategy_drawdown_pct",
            value=15.0,
            timestamp_ns=current_time_ns(),
            labels={"strategy_id": "beta"},
        )
        alerts2 = await manager.evaluate_rules(snapshot2)
        assert len(alerts2) == 1

        # Should have 2 active alerts (different strategy_id)
        assert len(manager.active_alerts) == 2

    def test_get_alert_key_includes_labels(self) -> None:
        """Test alert key includes metric labels for uniqueness."""
        bus = InMemoryBus()
        manager = AlertManager(bus=bus)

        rule = AlertRule(
            name="test_alert",
            metric="njord_test_metric",
            condition="> 10.0",
            duration=0,
            labels={},
            annotations={},
        )

        snapshot1 = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=current_time_ns(),
            labels={"strategy_id": "alpha"},
        )

        snapshot2 = MetricSnapshot(
            name="njord_test_metric",
            value=15.0,
            timestamp_ns=current_time_ns(),
            labels={"strategy_id": "beta"},
        )

        key1 = manager._get_alert_key(rule, snapshot1)
        key2 = manager._get_alert_key(rule, snapshot2)

        assert key1 != key2
        assert "alpha" in key1
        assert "beta" in key2
