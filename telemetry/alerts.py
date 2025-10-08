"""Alert manager for metric threshold violations.

This module implements an alert system that monitors metrics and fires
alerts when thresholds are breached for a specified duration.
"""

from __future__ import annotations

import logging
import operator
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from telemetry.contracts import Alert, MetricSnapshot

if TYPE_CHECKING:
    from core.bus import BusProto

logger = logging.getLogger(__name__)

# Operator mapping for condition evaluation
_OPERATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

# Deduplication window (5 minutes in nanoseconds)
_DEDUP_WINDOW_NS = 5 * 60 * 1_000_000_000


@dataclass
class AlertRule:
    """Alert rule loaded from YAML configuration.

    Attributes:
        name: Alert rule name
        metric: Metric name to monitor
        condition: Threshold condition (e.g., "> 10.0")
        duration: Duration in seconds condition must hold before firing
        labels: Alert labels (severity, etc.)
        annotations: Alert annotations (summary, description)
    """

    name: str
    metric: str
    condition: str
    duration: int
    labels: dict[str, str]
    annotations: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertRule:
        """Load alert rule from dictionary.

        Args:
            data: Dictionary with alert rule data

        Returns:
            AlertRule instance

        Raises:
            ValueError: If required fields missing
        """
        if "name" not in data:
            raise ValueError("Alert rule missing required field: name")
        if "metric" not in data:
            raise ValueError("Alert rule missing required field: metric")
        if "condition" not in data:
            raise ValueError("Alert rule missing required field: condition")

        return cls(
            name=data["name"],
            metric=data["metric"],
            condition=data["condition"],
            duration=data.get("duration", 0),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
        )


class AlertManager:
    """Alert manager for monitoring metric thresholds.

    Evaluates alert rules against incoming metrics and fires alerts
    when thresholds are breached for the configured duration.

    Attributes:
        bus: Event bus for publishing alerts
        rules: List of alert rules
        active_alerts: Dict mapping alert key to Alert instance
        last_fired: Dict mapping alert key to timestamp (for deduplication)
    """

    def __init__(self, bus: BusProto, rules_path: Path | None = None) -> None:
        """Initialize alert manager.

        Args:
            bus: Event bus for publishing alerts
            rules_path: Path to YAML file with alert rules (optional)
        """
        self.bus = bus
        self.rules: list[AlertRule] = []
        self.active_alerts: dict[str, Alert] = {}
        self.last_fired: dict[str, int] = {}

        if rules_path is not None:
            self.load_rules(rules_path)

    def load_rules(self, rules_path: Path) -> None:
        """Load alert rules from YAML file.

        Args:
            rules_path: Path to YAML file with alert rules

        Raises:
            FileNotFoundError: If rules file doesn't exist
            ValueError: If rules file is invalid
        """
        if not rules_path.exists():
            raise FileNotFoundError(f"Alert rules file not found: {rules_path}")

        with rules_path.open() as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Alert rules file must contain a YAML dictionary")

        if "alerts" not in data:
            raise ValueError("Alert rules file must have 'alerts' key")

        rules_data = data["alerts"]
        if not isinstance(rules_data, list):
            raise ValueError("'alerts' must be a list")

        self.rules = [AlertRule.from_dict(rule) for rule in rules_data]
        logger.info("alert_manager.rules_loaded", extra={"count": len(self.rules)})

    async def evaluate_rules(self, snapshot: MetricSnapshot) -> list[Alert]:
        """Evaluate alert rules against metric snapshot.

        Args:
            snapshot: Metric snapshot to evaluate

        Returns:
            List of alerts fired (state=firing)
        """
        fired_alerts: list[Alert] = []

        for rule in self.rules:
            if rule.metric != snapshot.name:
                continue

            # Evaluate condition
            if self._evaluate_condition(rule.condition, snapshot.value):
                alert = self._handle_condition_true(rule, snapshot)
                if alert is not None and alert.state == "firing":
                    fired_alerts.append(alert)
            else:
                # Condition no longer true - resolve alert
                self._handle_condition_false(rule, snapshot)

        return fired_alerts

    def _evaluate_condition(self, condition: str, value: float) -> bool:
        """Evaluate threshold condition.

        Args:
            condition: Condition string (e.g., "> 10.0", "<= 0.5")
            value: Current metric value

        Returns:
            True if condition is met, False otherwise
        """
        # Parse condition string
        parts = condition.strip().split(maxsplit=1)
        if len(parts) != 2:
            logger.warning(
                "alert_manager.invalid_condition",
                extra={"condition": condition},
            )
            return False

        op_str, threshold_str = parts
        if op_str not in _OPERATORS:
            logger.warning(
                "alert_manager.unknown_operator",
                extra={"operator": op_str, "condition": condition},
            )
            return False

        try:
            threshold = float(threshold_str)
        except ValueError:
            logger.warning(
                "alert_manager.invalid_threshold",
                extra={"threshold": threshold_str, "condition": condition},
            )
            return False

        op_func = _OPERATORS[op_str]
        return bool(op_func(value, threshold))

    def _handle_condition_true(self, rule: AlertRule, snapshot: MetricSnapshot) -> Alert | None:
        """Handle alert condition being true.

        Args:
            rule: Alert rule
            snapshot: Metric snapshot

        Returns:
            Alert instance if fired, None otherwise
        """
        alert_key = self._get_alert_key(rule, snapshot)

        # Check if alert already active
        if alert_key in self.active_alerts:
            existing_alert = self.active_alerts[alert_key]

            # Check if duration requirement met
            duration_elapsed_ns = snapshot.timestamp_ns - existing_alert.active_since_ns
            duration_elapsed_sec = duration_elapsed_ns / 1_000_000_000

            if duration_elapsed_sec >= rule.duration and existing_alert.state == "pending":
                # Fire alert
                fired_alert = replace(
                    existing_alert,
                    state="firing",
                    timestamp_ns=snapshot.timestamp_ns,
                )
                self.active_alerts[alert_key] = fired_alert
                return fired_alert

            # Still pending, update current value
            self.active_alerts[alert_key] = replace(
                existing_alert,
                current_value=snapshot.value,
                timestamp_ns=snapshot.timestamp_ns,
            )
            return None

        # Create new pending alert
        alert = Alert(
            name=rule.name,
            metric_name=snapshot.name,
            condition=rule.condition,
            current_value=snapshot.value,
            timestamp_ns=snapshot.timestamp_ns,
            labels={**rule.labels, **dict(snapshot.labels)},
            annotations=self._render_annotations(rule.annotations, snapshot),
            state="pending",
            duration_sec=rule.duration,
            active_since_ns=snapshot.timestamp_ns,
        )

        self.active_alerts[alert_key] = alert

        # If duration is 0, fire immediately
        if rule.duration == 0:
            fired_alert = replace(alert, state="firing")
            self.active_alerts[alert_key] = fired_alert
            return fired_alert

        return None

    def _handle_condition_false(self, rule: AlertRule, snapshot: MetricSnapshot) -> None:
        """Handle alert condition no longer being true.

        Args:
            rule: Alert rule
            snapshot: Metric snapshot
        """
        alert_key = self._get_alert_key(rule, snapshot)

        if alert_key in self.active_alerts:
            existing_alert = self.active_alerts[alert_key]

            if existing_alert.state == "firing":
                # Resolve the alert
                resolved_alert = replace(
                    existing_alert,
                    state="resolved",
                    current_value=snapshot.value,
                    timestamp_ns=snapshot.timestamp_ns,
                )
                # Don't keep resolved alerts in active_alerts
                del self.active_alerts[alert_key]

                # Publish resolved alert
                logger.info(
                    "alert_manager.alert_resolved",
                    extra={
                        "alert_name": resolved_alert.name,
                        "metric": resolved_alert.metric_name,
                    },
                )
            else:
                # Was pending, just remove it
                del self.active_alerts[alert_key]

    def _get_alert_key(self, rule: AlertRule, snapshot: MetricSnapshot) -> str:
        """Get unique key for alert.

        Args:
            rule: Alert rule
            snapshot: Metric snapshot

        Returns:
            Alert key string
        """
        # Include metric labels in key for uniqueness
        label_str = ",".join(f"{k}={v}" for k, v in sorted(snapshot.labels.items()))
        return f"{rule.name}:{snapshot.name}:{label_str}"

    def _render_annotations(
        self, annotations: dict[str, str], snapshot: MetricSnapshot
    ) -> dict[str, str]:
        """Render annotation templates with metric labels.

        Args:
            annotations: Annotation templates
            snapshot: Metric snapshot

        Returns:
            Rendered annotations
        """
        rendered: dict[str, str] = {}
        for key, template in annotations.items():
            # Simple template rendering: replace {{ $labels.key }} with value
            rendered_value = template
            for label_key, label_value in snapshot.labels.items():
                rendered_value = rendered_value.replace(
                    f"{{{{ $labels.{label_key} }}}}", label_value
                )
            rendered[key] = rendered_value
        return rendered

    async def fire_alert(self, alert: Alert) -> None:
        """Fire alert to configured channels.

        Args:
            alert: Alert to fire
        """
        # Check deduplication
        if self.deduplicate_alert(alert):
            logger.debug(
                "alert_manager.alert_deduplicated",
                extra={"alert_name": alert.name, "metric": alert.metric_name},
            )
            return

        # Log alert
        logger.warning(
            "alert_manager.alert_fired",
            extra={
                "alert_name": alert.name,
                "metric": alert.metric_name,
                "condition": alert.condition,
                "current_value": alert.current_value,
                "labels": dict(alert.labels),
                "annotations": dict(alert.annotations),
            },
        )

        # Publish to bus
        await self.bus.publish_json("telemetry.alerts", alert.to_dict())

        # Update last fired timestamp
        alert_key = f"{alert.name}:{alert.metric_name}"
        self.last_fired[alert_key] = alert.timestamp_ns

    def deduplicate_alert(self, alert: Alert) -> bool:
        """Check if alert is duplicate (within deduplication window).

        Args:
            alert: Alert to check

        Returns:
            True if duplicate (skip), False if new
        """
        alert_key = f"{alert.name}:{alert.metric_name}"

        if alert_key not in self.last_fired:
            return False

        last_fired_ns = self.last_fired[alert_key]
        time_since_last_ns = alert.timestamp_ns - last_fired_ns

        return time_since_last_ns < _DEDUP_WINDOW_NS

    async def process_metric(self, snapshot: MetricSnapshot) -> None:
        """Process metric snapshot and fire alerts if needed.

        This is a convenience method that evaluates rules and fires alerts.

        Args:
            snapshot: Metric snapshot to process
        """
        fired_alerts = await self.evaluate_rules(snapshot)
        for alert in fired_alerts:
            await self.fire_alert(alert)


def current_time_ns() -> int:
    """Get current time in nanoseconds since epoch.

    Returns:
        Current timestamp in nanoseconds
    """
    return int(time.time() * 1_000_000_000)
