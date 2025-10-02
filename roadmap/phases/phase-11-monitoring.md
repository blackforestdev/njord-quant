## Phase 11 — Monitoring & Alerts 📋

**Purpose:** Implement comprehensive alert system for operational events, risk violations, and performance anomalies.

**Current Status:** Phase 10 complete — Live Trade Controller fully operational
**Next Phase:** Phase 12 — Compliance & Audit

---

### Phase 11.0 — Alert Contracts 📋
**Status:** Planned
**Dependencies:** 10.9 (Controller Documentation)
**Task:** Define alert-specific contracts and notification types

**Contracts:**
```python
@dataclass(frozen=True)
class Alert:
    """Single alert event."""
    alert_id: str  # UUID
    timestamp_ns: int
    severity: Literal["info", "warning", "error", "critical"]
    category: Literal["system", "risk", "performance", "execution", "killswitch"]
    source: str  # Service name (risk_engine, paper_trader, etc.)
    title: str
    message: str
    labels: dict[str, str]  # e.g., {"strategy_id": "twap_v1", "symbol": "BTC/USDT"}
    annotations: dict[str, str]  # Additional context

@dataclass(frozen=True)
class AlertRule:
    """Alert rule definition."""
    rule_id: str
    name: str
    condition: str  # e.g., "drawdown_pct > 10.0"
    metric_name: str  # Metric to evaluate
    threshold: float
    duration_seconds: int  # How long condition must hold
    severity: Literal["info", "warning", "error", "critical"]
    channels: list[str]  # ["log", "redis", "webhook"]
    labels: dict[str, str]
    annotations: dict[str, str]
    enabled: bool

@dataclass(frozen=True)
class NotificationChannel:
    """Notification channel configuration."""
    channel_id: str
    channel_type: Literal["log", "redis", "webhook", "email", "slack"]
    config: dict[str, Any]  # Channel-specific config
    enabled: bool
    rate_limit_per_hour: int  # Max notifications per hour
```

**Files:**
- `alerts/contracts.py` (100 LOC)
- `tests/test_alert_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- Validation: severity/category enums valid, threshold > 0
- **NotificationChannel.rate_limit_per_hour enforced by AlertBus** (not individual channels)
- **Test verifies rate_limit_per_hour validation** (must be > 0)
- `make fmt lint type test` green

---

### Phase 11.1 — Alert Bus 📋
**Status:** Planned
**Dependencies:** 11.0 (Alert Contracts)
**Task:** Centralized alert routing and distribution

**Behavior:**
- Subscribe to alert sources (Redis topics, service logs, metric violations)
- Route alerts to configured channels based on severity/category
- Deduplication (suppress duplicate alerts within time window)
- Alert state tracking (active, resolved, acknowledged)
- Rate limiting per channel (prevent notification storms)
- Publish to Redis topic `alerts.fired` for persistence

**API:**
```python
class AlertBus:
    def __init__(
        self,
        bus: BusProto,
        channels: dict[str, NotificationChannel]
    ): ...

    async def publish_alert(self, alert: Alert) -> None:
        """Publish alert and route to channels.

        Behavior:
            - Check deduplication window (5 minutes by default)
            - Apply rate limits per channel
            - Route to channels matching severity threshold
            - Publish to alerts.fired topic for journaling
        """
        pass

    async def resolve_alert(self, alert_id: str) -> None:
        """Mark alert as resolved."""
        pass

    def should_suppress(
        self,
        alert: Alert,
        window_seconds: int = 300
    ) -> bool:
        """Check if alert should be suppressed (duplicate)."""
        pass

    async def route_to_channels(
        self,
        alert: Alert
    ) -> list[str]:
        """Determine which channels should receive alert.

        Returns:
            List of channel IDs that will receive alert
        """
        pass
```

**Deduplication Strategy:**
- Key: `(source, category, labels hash)`
- Window: 5 minutes (configurable)
- Store in Redis with TTL

**Files:**
- `alerts/bus.py` (200 LOC)
- `tests/test_alert_bus.py`

**Acceptance:**
- Publishes alerts to `alerts.fired` topic
- Deduplication prevents duplicate alerts within 5-minute window (Redis TTL-based)
- **Test verifies Redis TTL expiration for dedup keys** (key disappears after window)
- Rate limiting enforced per channel (max N/hour)
- **Test verifies rate limit blocks Nth+1 alert** (within same hour)
- **Test verifies rate limit resets after hour boundary**
- Alert routing based on severity thresholds
- **Test verifies severity filtering** (critical alert skips info-only channels)
- Test includes deduplication and rate limit scenarios
- `make fmt lint type test` green

---

### Phase 11.2 — Rule Engine 📋
**Status:** Planned
**Dependencies:** 11.1 (Alert Bus)
**Task:** Evaluate alert rules against metrics and events

**Behavior:**
- Load alert rules from YAML config (`config/alerts.yaml`)
- Subscribe to `telemetry.metrics` topic
- Evaluate rules against incoming metrics
- Track condition duration (must hold for N seconds)
- Fire alerts when thresholds breached for duration
- Auto-resolve when condition clears
- Support simple conditions: `>`, `<`, `>=`, `<=`, `==`, `!=`

**Alert Rules Config:**
```yaml
# config/alerts.yaml
rules:
  - rule_id: high_drawdown
    name: "High Strategy Drawdown"
    metric_name: njord_strategy_drawdown_pct
    condition: "> 10.0"
    duration_seconds: 60
    severity: critical
    channels: [log, redis, webhook]
    labels:
      category: performance
    annotations:
      summary: "Strategy {{ $labels.strategy_id }} drawdown exceeded 10%"
      runbook: "https://wiki.internal/runbooks/high-drawdown"

  - rule_id: killswitch_trip
    name: "Kill Switch Triggered"
    metric_name: njord_killswitch_trips_total
    condition: "> 0"
    duration_seconds: 1
    severity: critical
    channels: [log, redis, webhook]
    labels:
      category: killswitch
    annotations:
      summary: "Kill switch has been tripped"

  - rule_id: risk_rejection_rate
    name: "High Risk Rejection Rate"
    metric_name: njord_intents_denied_total
    condition: "> 100"
    duration_seconds: 300  # 5 minutes
    severity: warning
    channels: [log]
    labels:
      category: risk
```

**API:**
```python
class RuleEngine:
    def __init__(
        self,
        bus: BusProto,
        alert_bus: AlertBus,
        config_path: Path
    ): ...

    async def load_rules(self) -> None:
        """Load alert rules from YAML config."""
        pass

    async def evaluate_metric(
        self,
        snapshot: MetricSnapshot
    ) -> None:
        """Evaluate metric against all matching rules."""
        pass

    def check_condition(
        self,
        rule: AlertRule,
        value: float
    ) -> bool:
        """Check if metric value meets rule condition.

        Supports: >, <, >=, <=, ==, !=
        """
        pass

    async def track_duration(
        self,
        rule_id: str,
        breached: bool,
        timestamp_ns: int
    ) -> bool:
        """Track how long condition has held.

        Returns:
            True if duration threshold met (should fire alert)
        """
        pass

    def render_annotations(
        self,
        rule: AlertRule,
        labels: dict[str, str]
    ) -> dict[str, str]:
        """Render annotation templates with label substitution.

        Example: "{{ $labels.strategy_id }}" → "twap_v1"
        """
        pass
```

**Files:**
- `alerts/rules.py` (250 LOC)
- `tests/test_rule_engine.py`

**Acceptance:**
- Loads rules from `config/alerts.yaml`
- Evaluates conditions correctly (>, <, >=, <=, ==, !=)
- Duration tracking works (fires only after N seconds)
- Auto-resolves when condition clears
- Annotation template rendering works (label substitution)
- Test includes duration tracking and auto-resolve scenarios
- `make fmt lint type test` green

---

### Phase 11.3 — Log Notification Channel 📋
**Status:** Planned
**Dependencies:** 11.2 (Rule Engine)
**Task:** Log-based notification channel (always available)

**Behavior:**
- Write alerts to structured log (NDJSON)
- Separate alert log: `var/log/njord/alerts.ndjson`
- Include full alert context (severity, category, labels, annotations)
- No external dependencies (always works)
- Rotation handled externally (not inline)

**API:**
```python
class LogNotificationChannel:
    def __init__(
        self,
        log_path: Path = Path("var/log/njord/alerts.ndjson")
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Write alert to log file.

        Returns:
            True if successful, False if failed
        """
        pass

    def format_alert(self, alert: Alert) -> str:
        """Format alert as NDJSON line."""
        pass
```

**Files:**
- `alerts/channels/log.py` (60 LOC)
- `tests/test_log_channel.py`

**Acceptance:**
- Alerts written to `var/log/njord/alerts.ndjson`
- NDJSON format (one alert per line)
- Includes all alert fields (severity, category, labels, annotations)
- No external dependencies
- Test verifies alert persistence
- `make fmt lint type test` green

---

### Phase 11.4 — Redis Notification Channel 📋
**Status:** Planned
**Dependencies:** 11.3 (Log Notification Channel)
**Task:** Publish alerts to Redis pub/sub for real-time consumption

**Behavior:**
- Publish alerts to Redis topic `alerts.notifications`
- Other services can subscribe for real-time alerts
- Fallback to log channel if Redis unavailable
- No persistence (pub/sub only)

**API:**
```python
class RedisNotificationChannel:
    def __init__(
        self,
        bus: BusProto,
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Publish alert to Redis topic.

        Returns:
            True if successful, False if failed (uses fallback)
        """
        pass
```

**Files:**
- `alerts/channels/redis.py` (50 LOC)
- `tests/test_redis_channel.py`

**Acceptance:**
- Publishes to `alerts.notifications` topic
- Fallback to log channel if Redis unavailable
- Test verifies Redis publish
- Test verifies fallback behavior
- `make fmt lint type test` green

---

### Phase 11.5 — Webhook Notification Channel 📋
**Status:** Planned
**Dependencies:** 11.4 (Redis Notification Channel)
**Task:** HTTP webhook notification for external integrations

**Behavior:**
- POST alerts to configured webhook URL
- JSON payload format
- Retry logic (3 attempts with exponential backoff)
- Timeout: 5 seconds per attempt
- Fallback to log channel if all retries fail
- **Security: No secrets in config** (use env vars for URLs/tokens)

**Webhook Payload:**
```json
{
  "alert_id": "uuid",
  "timestamp": 1234567890000000000,
  "severity": "critical",
  "category": "killswitch",
  "source": "risk_engine",
  "title": "Kill Switch Triggered",
  "message": "Kill switch has been tripped",
  "labels": {"env": "live"},
  "annotations": {"runbook": "https://..."}
}
```

**API:**
```python
class WebhookNotificationChannel:
    def __init__(
        self,
        webhook_url: str,
        auth_token: str | None = None,  # From env var
        timeout_seconds: int = 5,
        max_retries: int = 3,
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """POST alert to webhook URL.

        Returns:
            True if successful, False if all retries failed
        """
        pass

    async def send_with_retry(
        self,
        payload: dict[str, Any]
    ) -> bool:
        """Send with exponential backoff retry."""
        pass
```

**Config Example:**
```yaml
# config/alerts.yaml
channels:
  webhook_primary:
    type: webhook
    url: "${NJORD_ALERT_WEBHOOK_URL}"  # From env var
    auth_token: "${NJORD_ALERT_WEBHOOK_TOKEN}"  # From env var
    enabled: true
    rate_limit_per_hour: 100
```

**Files:**
- `alerts/channels/webhook.py` (120 LOC)
- `tests/test_webhook_channel.py`

**Acceptance:**
- POSTs JSON payload to webhook URL
- Retry logic (3 attempts, exponential backoff)
- Timeout enforcement (5 seconds)
- Auth token from env var (not hardcoded)
- Fallback to log channel on failure
- Test includes retry and timeout scenarios
- `make fmt lint type test` green

---

### Phase 11.6 — Email Notification Channel (Stub) 📋
**Status:** Planned
**Dependencies:** 11.5 (Webhook Notification Channel)
**Task:** Email notification stub (no SMTP in Phase 11)

**Behavior:**
- Email channel stub for future implementation
- Logs email intent to alert log
- **No actual SMTP sending** (deferred to deployment)
- Config structure defined (SMTP host, port, credentials)
- Placeholder for future implementation

**API:**
```python
class EmailNotificationChannel:
    def __init__(
        self,
        smtp_config: dict[str, Any],
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Email notification (stub implementation).

        Current behavior:
            - Logs email intent to alert log
            - Returns True (no actual sending)

        Future implementation:
            - Connect to SMTP server
            - Send formatted email
            - Handle authentication
        """
        pass

    def format_email(self, alert: Alert) -> dict[str, str]:
        """Format alert as email (subject, body).

        Returns:
            {"subject": "...", "body": "...", "to": "..."}
        """
        pass
```

**Config Example:**
```yaml
# config/alerts.yaml
channels:
  email_ops:
    type: email
    smtp_host: "${NJORD_SMTP_HOST}"
    smtp_port: 587
    smtp_user: "${NJORD_SMTP_USER}"
    smtp_pass: "${NJORD_SMTP_PASS}"
    from_addr: "alerts@trading.internal"
    to_addrs: ["ops@trading.internal"]
    enabled: false  # Stub only in Phase 11
```

**Files:**
- `alerts/channels/email.py` (80 LOC stub)
- `tests/test_email_channel.py`

**Acceptance:**
- Logs email intent (no actual sending)
- Config structure defined (SMTP params)
- Email formatting works (subject, body)
- Returns success (stub always succeeds)
- Test verifies stub behavior (logs, no network I/O)
- `make fmt lint type test` green

---

### Phase 11.7 — Slack Notification Channel (Stub) 📋
**Status:** Planned
**Dependencies:** 11.6 (Email Notification Channel)
**Task:** Slack notification stub (no Slack API in Phase 11)

**Behavior:**
- Slack channel stub for future implementation
- Logs Slack intent to alert log
- **No actual Slack API calls** (deferred to deployment)
- Config structure defined (webhook URL, channel)
- Placeholder for future implementation

**API:**
```python
class SlackNotificationChannel:
    def __init__(
        self,
        webhook_url: str,  # Slack webhook URL
        channel: str,  # e.g., "#alerts"
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Slack notification (stub implementation).

        Current behavior:
            - Logs Slack intent to alert log
            - Returns True (no actual sending)

        Future implementation:
            - POST to Slack webhook URL
            - Format message with blocks/attachments
            - Handle rate limits
        """
        pass

    def format_slack_message(self, alert: Alert) -> dict[str, Any]:
        """Format alert as Slack message.

        Returns:
            Slack message payload (blocks format)
        """
        pass
```

**Slack Message Format:**
```json
{
  "channel": "#alerts",
  "username": "Njord Alerts",
  "icon_emoji": ":rotating_light:",
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "🚨 Kill Switch Triggered"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Severity:*\ncritical"},
        {"type": "mrkdwn", "text": "*Source:*\nrisk_engine"}
      ]
    }
  ]
}
```

**Config Example:**
```yaml
# config/alerts.yaml
channels:
  slack_ops:
    type: slack
    webhook_url: "${NJORD_SLACK_WEBHOOK_URL}"
    channel: "#alerts"
    enabled: false  # Stub only in Phase 11
```

**Files:**
- `alerts/channels/slack.py` (100 LOC stub)
- `tests/test_slack_channel.py`

**Acceptance:**
- Logs Slack intent (no actual sending)
- Config structure defined (webhook URL, channel)
- Slack message formatting works (blocks format)
- Returns success (stub always succeeds)
- Test verifies stub behavior (logs, no network I/O)
- `make fmt lint type test` green

---

### Phase 11.8 — Alert Service Daemon 📋
**Status:** Planned
**Dependencies:** 11.7 (Slack Notification Channel)
**Task:** Long-running alert service orchestrating all components

**Behavior:**
- Orchestrate AlertBus, RuleEngine, and all channels
- Subscribe to metrics and events
- Evaluate rules in real-time
- Route alerts to configured channels
- **Production gating: Check env var NJORD_ENABLE_ALERTS=1 before starting** (disabled by default)
- **Graceful degradation: If disabled, only expose health check** (no alert routing)
- Health check endpoint (HTTP `/health`)
- Graceful shutdown (SIGTERM handling)
- **Bind to localhost by default** (127.0.0.1)

**API:**
```python
class AlertService:
    def __init__(
        self,
        config: Config,
        bus: BusProto,
        bind_host: str = "127.0.0.1",
        health_port: int = 9092
    ): ...

    async def start(self) -> None:
        """Start alert service.

        Tasks:
            - Check NJORD_ENABLE_ALERTS=1 env var (exit early if disabled)
            - Load alert rules from config
            - Initialize notification channels
            - Start alert bus
            - Subscribe to telemetry.metrics
            - Expose health check endpoint

        Security:
            - Alert routing disabled by default (requires NJORD_ENABLE_ALERTS=1)
            - Prevents accidental alert noise during maintenance/testing
            - Health check always available (even when disabled)
        """
        pass

    async def run(self) -> None:
        """Main event loop."""
        pass

    async def health_check(self) -> dict[str, Any]:
        """Health check endpoint.

        Returns:
            {"status": "healthy", "rules_loaded": N, "channels_active": [...]}
        """
        pass

    async def shutdown(self) -> None:
        """Graceful shutdown (SIGTERM handler)."""
        pass
```

**Files:**
- `apps/alert_service/main.py` (200 LOC)
- `tests/test_alert_service.py`

**Acceptance:**
- Loads rules from `config/alerts.yaml`
- **Alert routing gated by NJORD_ENABLE_ALERTS=1 env var** (disabled by default)
- **Test verifies service exits early when NJORD_ENABLE_ALERTS unset** (no alert routing)
- **Test verifies health check works even when alerts disabled**
- Evaluates metrics in real-time (when enabled)
- Routes alerts to channels based on severity (when enabled)
- Health check accessible at `http://localhost:9092/health`
- **Security: Binds to localhost (127.0.0.1) by default**
- Graceful shutdown on SIGTERM
- Test includes end-to-end alert flow (metric → rule → channel) when enabled
- `make fmt lint type test` green

---

### Phase 11.9 — Alert CLI 📋
**Status:** Planned
**Dependencies:** 11.8 (Alert Service Daemon)
**Task:** CLI for alert management and testing

**Behavior:**
- List active alerts
- Fire test alert (for channel testing)
- Acknowledge/resolve alerts
- List configured rules
- Validate alert config
- Subscribe to live alerts (streaming)

**CLI Commands:**
```bash
# List active alerts
python -m alerts.cli list --severity critical

# Fire test alert
python -m alerts.cli test \
    --severity critical \
    --category system \
    --message "Test alert"

# Acknowledge alert
python -m alerts.cli ack <alert_id>

# Resolve alert
python -m alerts.cli resolve <alert_id>

# List alert rules
python -m alerts.cli rules --enabled-only

# Validate config
python -m alerts.cli validate --config config/alerts.yaml

# Stream live alerts (subscribe)
python -m alerts.cli stream --follow
```

**API:**
```python
class AlertCLI:
    def __init__(self, bus: BusProto, config_path: Path): ...

    async def list_alerts(
        self,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 50
    ) -> None:
        """List active alerts."""
        pass

    async def fire_test_alert(
        self,
        severity: str,
        category: str,
        message: str
    ) -> None:
        """Fire test alert for channel testing."""
        pass

    async def acknowledge_alert(self, alert_id: str) -> None:
        """Acknowledge alert."""
        pass

    async def resolve_alert(self, alert_id: str) -> None:
        """Resolve alert."""
        pass

    async def list_rules(self, enabled_only: bool = False) -> None:
        """List configured alert rules."""
        pass

    async def validate_config(self, config_path: Path) -> None:
        """Validate alert config (rules, channels)."""
        pass

    async def stream_alerts(self, follow: bool = False) -> None:
        """Subscribe to live alerts (streaming output)."""
        pass
```

**Files:**
- `alerts/cli.py` (250 LOC)
- `tests/test_alert_cli.py`

**Acceptance:**
- List alerts with filtering (severity, category)
- Test alert fires to all channels
- Acknowledge/resolve updates alert state
- Rules listing shows enabled/disabled status
- Config validation catches errors (invalid conditions, missing fields)
- Stream mode outputs alerts in real-time
- All CLI commands have --help text
- `make fmt lint type test` green

---

### Phase 11.10 — Alert Documentation 📋
**Status:** Planned
**Dependencies:** 11.9 (Alert CLI)
**Task:** Comprehensive documentation for alert system

**Deliverables:**

**1. Alert System Architecture (docs/alerts/ARCHITECTURE.md)**
- Component diagram (AlertBus, RuleEngine, Channels)
- Data flow: Metric → Rule → Alert → Channel → Notification
- Deduplication and rate limiting strategy
- Integration with Phase 9 (Metrics) and Phase 10 (Controller)

**2. Alert Rules Guide (docs/alerts/RULES.md)**
- Rule configuration format
- Condition syntax (>, <, >=, <=, ==, !=)
- Duration tracking mechanics
- Annotation templating
- Example rules for common scenarios

**3. Channel Configuration (docs/alerts/CHANNELS.md)**
- Channel types: log, redis, webhook, email (stub), slack (stub)
- Security best practices (env vars for secrets)
- Rate limiting configuration
- Fallback strategies

**4. Operations Runbook (docs/alerts/RUNBOOK.md)**
- Starting alert service
- Testing alert channels
- Troubleshooting alert delivery
- Common alert scenarios and responses

**5. API Reference (docs/alerts/API.md)**
- Alert contracts reference
- AlertBus API
- RuleEngine API
- NotificationChannel interface
- CLI command reference

**Files:**
- `docs/alerts/ARCHITECTURE.md`
- `docs/alerts/RULES.md`
- `docs/alerts/CHANNELS.md`
- `docs/alerts/RUNBOOK.md`
- `docs/alerts/API.md`

**Acceptance:**
- Architecture diagram shows all components
- Rules guide includes 5+ example rules
- Channels guide covers all supported types
- Runbook includes troubleshooting steps
- API reference documents all public interfaces
- All docs use consistent formatting (markdown)
- `make fmt lint type test` green (no code changes)

---

## Dependencies Summary

```
Phase 10 (Live Trade Controller) ✅
    └─> Phase 11.0 (Alert Contracts) — Alert, AlertRule, NotificationChannel
            └─> 11.1 (Alert Bus) — Routing, deduplication, rate limiting
                    └─> 11.2 (Rule Engine) — Metric evaluation, duration tracking
                            └─> 11.3 (Log Channel) — NDJSON alert logging
                                    └─> 11.4 (Redis Channel) — Pub/sub notifications
                                            └─> 11.5 (Webhook Channel) — HTTP POST with retry
                                                    └─> 11.6 (Email Channel) — Stub implementation
                                                            └─> 11.7 (Slack Channel) — Stub implementation
                                                                    └─> 11.8 (Alert Service) — Daemon orchestration
                                                                            └─> 11.9 (Alert CLI) — Management commands
                                                                                    └─> 11.10 (Documentation) — Guides and API reference
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---
