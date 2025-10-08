## Phase 9 — Metrics & Telemetry 🚧

**Purpose:** Implement comprehensive observability with Prometheus metrics, Grafana dashboards, and real-time performance tracking.

**Current Status:** Phase 8 complete — Execution Layer fully operational
**Next Phase:** Phase 10 — Live Trade Controller

---

### Phase 9.0 — Metrics Contracts ✅
**Status:** Complete
**Dependencies:** 8.9 (Execution Performance Metrics)
**Task:** Define telemetry-specific contracts and metric types

**Contracts:**
```python
@dataclass(frozen=True)
class MetricSnapshot:
    """Single metric measurement."""
    name: str
    value: float
    timestamp_ns: int
    labels: dict[str, str]  # e.g., {"strategy_id": "twap_v1", "symbol": "ATOM/USDT"}
    metric_type: Literal["counter", "gauge", "histogram", "summary"]

@dataclass(frozen=True)
class StrategyMetrics:
    """Strategy-level performance metrics."""
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

@dataclass(frozen=True)
class SystemMetrics:
    """System-level health metrics."""
    timestamp_ns: int
    bus_messages_sent: int
    bus_messages_received: int
    journal_writes: int
    journal_bytes: int
    active_subscriptions: int
    event_loop_lag_ms: float
    memory_usage_mb: float
```

**Files:**
- `telemetry/contracts.py` (80 LOC)
- `tests/test_telemetry_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Metric types follow Prometheus conventions
- Serializable to/from dict
- Labels support cardinality limits (warn if >100 unique combos)
- `make fmt lint type test` green

---

### Phase 9.1 — Prometheus Metrics Exporter ✅
**Status:** Complete
**Dependencies:** 9.0 (Metrics Contracts)
**Task:** Implement Prometheus-compatible metrics HTTP endpoint

**Behavior:**
- Expose metrics at `/metrics` endpoint (HTTP server on configurable port)
- Support standard Prometheus metric types: Counter, Gauge, Histogram, Summary
- Aggregate metrics from all services via Redis pub/sub
- Follow Prometheus naming conventions (snake_case, `_total` suffix for counters)
- Include help text and type hints in exposition format
- Support metric labels with cardinality protection

**API:**
```python
class PrometheusExporter:
    def __init__(
        self,
        bus: BusProto,
        port: int = 9090,
        bind_host: str = "127.0.0.1",  # Localhost-only by default
        registry: MetricRegistry | None = None
    ): ...

    async def start(self) -> None:
        """Start HTTP server for /metrics endpoint.

        Security:
            - Binds to localhost (127.0.0.1) by default
            - For production with Prometheus scraper on different host, explicitly set bind_host
            - Optional: Require Bearer token via env var NJORD_METRICS_TOKEN
        """
        pass

    async def collect_metrics(self) -> str:
        """Collect all metrics and format for Prometheus.

        Returns:
            Metrics in Prometheus exposition format
        """
        pass

    def register_counter(
        self,
        name: str,
        help_text: str,
        labels: list[str] | None = None
    ) -> Counter:
        """Register a counter metric."""
        pass

    def register_gauge(
        self,
        name: str,
        help_text: str,
        labels: list[str] | None = None
    ) -> Gauge:
        """Register a gauge metric."""
        pass

    def register_histogram(
        self,
        name: str,
        help_text: str,
        buckets: list[float],
        labels: list[str] | None = None
    ) -> Histogram:
        """Register a histogram metric."""
        pass
```

**Standard Metrics:**
```
# Counters
njord_orders_total{strategy_id, symbol, side}
njord_fills_total{strategy_id, symbol, side}
njord_risk_rejections_total{reason}
njord_bus_messages_total{topic, direction}

# Gauges
njord_active_positions{strategy_id, symbol}
njord_portfolio_equity_usd{portfolio_id}
njord_strategy_pnl_usd{strategy_id}
njord_event_loop_lag_seconds

# Histograms
njord_fill_latency_seconds{strategy_id}
njord_order_size_usd{strategy_id, symbol}
njord_execution_slippage_bps{algo_type}
```

**Files:**
- `telemetry/prometheus.py` (250 LOC)
- `telemetry/registry.py` (100 LOC for metric storage)
- `tests/test_prometheus_exporter.py`

**Acceptance:**
- HTTP endpoint serves metrics on `/metrics`
- **Security: Binds to localhost (127.0.0.1) by default** (prevents public exposure)
- **Security: Optional Bearer token auth via NJORD_METRICS_TOKEN env var**
- Exposition format valid (Prometheus scraper compatible)
- Counter increments persisted across scrapes
- Gauge updates reflect latest values
- Histogram buckets correctly categorize observations
- Cardinality protection warns/rejects high-cardinality labels
- Test includes scraping simulation (with/without auth token)
- `make fmt lint type test` green

---

### Phase 9.2 — Service Instrumentation ✅
**Status:** Complete
**Dependencies:** 9.1 (Prometheus Metrics Exporter)
**Task:** Instrument core services with metrics collection

**Behavior:**
- Add metrics collection to risk_engine, paper_trader, broker, strategy_runner
- Emit metrics to Redis topic `telemetry.metrics`
- Prometheus exporter subscribes and aggregates
- Use decorators for common patterns (timing, counting)
- **Production gating: Check env var NJORD_ENABLE_METRICS=1 before emitting** (disabled in tests)
- **Fallback: If Redis/bus unavailable, log metrics locally** (no service failure)
- Minimal performance overhead (<1% latency increase)

**Instrumentation Points:**

**Risk Engine:**
```python
# Counters
- njord_intents_received_total
- njord_intents_allowed_total
- njord_intents_denied_total{reason}
- njord_killswitch_trips_total

# Histograms
- njord_risk_check_duration_seconds
```

**Paper Trader / Broker:**
```python
# Counters
- njord_orders_placed_total{venue}
- njord_fills_generated_total{venue}

# Gauges
- njord_open_orders{symbol}
- njord_position_size{strategy_id, symbol}

# Histograms
- njord_fill_price_deviation_bps
```

**Strategy Runner:**
```python
# Counters
- njord_signals_generated_total{strategy_id}
- njord_strategy_errors_total{strategy_id}

# Histograms
- njord_signal_generation_duration_seconds{strategy_id}
```

**Helper Decorators:**
```python
@count_calls(metric_name="njord_function_calls_total")
async def handle_intent(self, intent: OrderIntent) -> None:
    ...

@measure_duration(metric_name="njord_processing_duration_seconds")
async def process_event(self, event: TradeEvent) -> None:
    ...
```

**Files:**
- `telemetry/decorators.py` (80 LOC)
- Update `apps/risk_engine/main.py` (+50 LOC)
- Update `apps/paper_trader/main.py` (+50 LOC)
- Update `apps/broker_binanceus/main.py` (+50 LOC)
- Update `apps/strategy_runner/main.py` (+50 LOC)
- `tests/test_service_instrumentation.py`

**Acceptance:**
- All core services emit metrics to `telemetry.metrics` topic
- **Metrics emission gated by NJORD_ENABLE_METRICS=1 env var** (disabled by default in tests)
- **Graceful degradation: Metrics failures don't crash services** (log + continue)
- Decorators correctly measure duration and count calls
- Metrics include appropriate labels (strategy_id, symbol, etc.)
- Performance overhead <1% (benchmark test)
- Test verifies metrics disabled when NJORD_ENABLE_METRICS unset
- Test verifies service continues if bus unavailable (fallback to local logging)
- `make fmt lint type test` green

**Polish / Follow-ups:**
- Revalidate external consumers of `RiskEngine.handle_intent` now that the method returns `(allowed, reason)`
- Consider increasing iterations in the performance benchmark to reduce flakiness risk
- Add docstrings noting metrics emission on instrumented service methods
- Reconfirm `StrategyManager` metrics once broader instrumentation dependencies land

---

### Phase 9.3 — Grafana Dashboard Configs ✅
**Status:** Complete
**Dependencies:** 9.2 (Service Instrumentation)
**Task:** Create Grafana dashboard JSON configs for visualization

**Deliverables:**

**1. System Health Dashboard**
- Event loop lag over time
- Bus message throughput (messages/sec)
- Memory usage per service
- Journal write rates
- Active subscriptions count

**2. Trading Activity Dashboard**
- Orders sent/filled/rejected (rate and count)
- Fill latency distribution (P50, P95, P99)
- Position sizes by strategy
- Daily PnL by strategy (bar chart)
- Risk rejection reasons (pie chart)

**3. Strategy Performance Dashboard**
- Equity curves (multi-strategy overlay)
- Sharpe ratio comparison (bar chart)
- Win rate by strategy (gauge)
- Max drawdown by strategy (gauge)
- Signal generation rate

**4. Execution Quality Dashboard**
- Execution slippage by algorithm (TWAP/VWAP/Iceberg/POV)
- Implementation shortfall distribution
- Venue fill rates
- Order size distribution (histogram)

**Dashboard Features:**
- Variable selectors: strategy_id, symbol, time range
- Alerts on critical thresholds (drawdown >10%, lag >100ms)
- Drill-down from summary to detail views
- Auto-refresh every 5 seconds

**Files:**
- `deploy/grafana/system_health.json` (dashboard config)
- `deploy/grafana/trading_activity.json`
- `deploy/grafana/strategy_performance.json`
- `deploy/grafana/execution_quality.json`
- `deploy/grafana/datasources.yaml` (Prometheus config)
- `deploy/grafana/README.md` (import instructions)
- `tests/test_dashboard_validity.py` (JSON schema validation)

**Acceptance:**
- Dashboard JSONs valid (Grafana import succeeds)
- All panels query correct Prometheus metrics
- Variable selectors work (tested with mock data)
- Alerts configured with reasonable thresholds
- README includes import and setup instructions
- Test validates JSON structure
- `make fmt lint type test` green

**Polish / Follow-ups (Phase 9.3):**
- Once later telemetry phases ship additional metrics (`njord_memory_usage_mb`, `njord_fill_latency_seconds_bucket`, etc.), revisit dashboards to confirm those panels populate correctly

---

### Phase 9.4 — Metric Aggregation Service ✅
**Status:** Complete
**Dependencies:** 9.3 (Grafana Dashboard Configs)
**Task:** Centralized service for metric aggregation and persistence

**Behavior:**
- Subscribe to `telemetry.metrics` topic
- Aggregate metrics in memory (rolling windows)
- Persist aggregated metrics to journal
- **Publish aggregated rollups to shared MetricRegistry** (consumed by PrometheusExporter)
- **Integration: PrometheusExporter reads from same MetricRegistry instance** (passed in constructor)
- **Flow: Raw metrics → Aggregator → Registry → Exporter → Prometheus scraper**
- Support metric downsampling (1m → 5m → 1h → 1d)
- Handle late-arriving metrics (grace period)

**API:**
```python
class MetricAggregator:
    def __init__(
        self,
        bus: BusProto,
        journal_dir: Path,
        registry: MetricRegistry,  # Shared with PrometheusExporter
        retention_hours: int = 168  # 7 days
    ): ...

    async def run(self) -> None:
        """Main aggregation loop."""
        pass

    async def aggregate_metrics(
        self,
        snapshot: MetricSnapshot
    ) -> None:
        """Aggregate incoming metric snapshot."""
        pass

    def downsample_to_interval(
        self,
        metrics: list[MetricSnapshot],
        interval_seconds: int
    ) -> list[MetricSnapshot]:
        """Downsample metrics to interval (avg for gauges, sum for counters)."""
        pass

    def flush_to_journal(self) -> None:
        """Persist aggregated metrics to journal."""
        pass

    def publish_to_registry(self, metrics: list[MetricSnapshot]) -> None:
        """Publish aggregated metrics to shared MetricRegistry.

        CRITICAL: This is how PrometheusExporter accesses aggregated data.
        Both aggregator and exporter must share the same MetricRegistry instance.
        """
        pass
```

**Aggregation Rules:**
- Counters: Sum over interval
- Gauges: Average over interval (or last value)
- Histograms: Merge buckets
- Summary: Combine percentiles

**Files:**
- `apps/metric_aggregator/main.py` (200 LOC)
- `telemetry/aggregation.py` (150 LOC)
- `tests/test_metric_aggregator.py`

**Acceptance:**
- Subscribes to `telemetry.metrics` and aggregates
- **CRITICAL: Publishes aggregated metrics to shared MetricRegistry** (PrometheusExporter integration)
- **Test verifies MetricRegistry contains aggregated rollups** (not just raw metrics)
- **Integration test: Aggregator + Exporter share same registry, exporter serves aggregated data**
- Downsampling produces correct values (sum for counters, avg for gauges)
- Journal persistence includes timestamp and labels
- Late metrics handled within grace period (5 minutes)
- Memory bounded (rolling window eviction)
- Test includes downsample validation
- `make fmt lint type test` green

---

### Phase 9.5 — Performance Attribution ✅
**Status:** Complete
**Dependencies:** 9.4 (Metric Aggregation Service)
**Task:** Attribute portfolio performance to individual strategies

**Behavior:**
- Track strategy contributions to portfolio PnL
- Calculate attribution metrics (absolute, relative, risk-adjusted)
- Identify performance drivers (alpha vs. beta)
- Compare strategy performance vs. benchmark
- Generate attribution reports

**API:**
```python
class PerformanceAttribution:
    def __init__(
        self,
        data_reader: DataReader,
        portfolio_id: str
    ): ...

    def calculate_attribution(
        self,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> AttributionReport:
        """Calculate performance attribution.

        Returns:
            Attribution report with strategy contributions
        """
        pass

    def attribute_pnl(
        self,
        portfolio_pnl: float,
        strategy_pnls: dict[str, float],
        strategy_weights: dict[str, float]
    ) -> dict[str, float]:
        """Attribute portfolio PnL to strategies.

        Returns:
            Dict mapping strategy_id to attributed PnL
        """
        pass

    def calculate_alpha_beta(
        self,
        strategy_returns: list[float],
        benchmark_returns: list[float]
    ) -> tuple[float, float]:
        """Calculate alpha and beta vs. benchmark.

        Returns:
            (alpha, beta) tuple
        """
        pass
```

**Attribution Methods:**
- Brinson attribution (allocation + selection effects)
- Factor-based attribution (decompose by risk factors)
- Risk-adjusted attribution (Sharpe/Sortino weighted)

**Files:**
- `telemetry/attribution.py` (200 LOC)
- `tests/test_performance_attribution.py`

**Acceptance:**
- PnL attribution matches portfolio total (sum test)
- Alpha/beta calculation matches manual computation
- Brinson attribution decomposes correctly
- Handles missing strategy data gracefully
- Test includes known attribution scenarios
- `make fmt lint type test` green

---

### Phase 9.6 — Real-Time Metrics Dashboard ✅
**Status:** Complete
**Dependencies:** 9.5 (Performance Attribution)
**Task:** Web-based real-time metrics dashboard (optional HTML/JS)

**Behavior:**
- Lightweight web dashboard served on HTTP port
- Auto-refresh metrics every 1 second (WebSocket or SSE)
- Display key metrics: PnL, positions, orders, risk status
- No external dependencies (embedded HTML/CSS/JS)
- Read-only view (no controls)

**API:**
```python
class MetricsDashboard:
    def __init__(
        self,
        bus: BusProto,
        port: int = 8080,
        bind_host: str = "127.0.0.1"  # Localhost-only by default
    ): ...

    async def start(self) -> None:
        """Start dashboard HTTP server.

        Security:
            - Binds to localhost (127.0.0.1) by default
            - For production access from other hosts, explicitly set bind_host
            - Optional: Require Bearer token via env var NJORD_DASHBOARD_TOKEN
        """
        pass

    async def stream_metrics(self) -> AsyncIterator[dict[str, Any]]:
        """Stream metrics updates via SSE."""
        pass

    def render_dashboard(self) -> str:
        """Render dashboard HTML."""
        pass
```

**Dashboard Sections:**
- Portfolio Summary (equity, daily PnL, positions count)
- Strategy Performance (Sharpe, win rate, PnL)
- Risk Status (kill-switch, caps utilization)
- Recent Activity (last 10 orders/fills)
- System Health (bus lag, memory usage)

**Files:**
- `apps/metrics_dashboard/main.py` (150 LOC)
- `apps/metrics_dashboard/templates/dashboard.html` (embedded)
- `tests/test_metrics_dashboard.py`

**Acceptance:**
- Dashboard accessible at `http://localhost:8080`
- **Security: Binds to localhost (127.0.0.1) by default** (prevents public exposure)
- **Security: Optional Bearer token auth via NJORD_DASHBOARD_TOKEN env var**
- Metrics update in real-time (1 sec refresh)
- All sections display correct data
- No external JS libraries (vanilla JS only)
- Mobile-responsive layout
- Test includes auth enforcement (valid/invalid token scenarios)
- `make fmt lint type test` green

---

### Phase 9.7 — Metric Alerts 📋
**Status:** Planned
**Dependencies:** 9.6 (Real-Time Metrics Dashboard)
**Task:** Alert system for metric threshold violations

**Behavior:**
- Define alert rules in YAML config
- Evaluate rules against incoming metrics
- Fire alerts when thresholds breached
- Support alert channels: log, Redis pub/sub, webhook (no Slack/email in phase 9)
- Deduplication (avoid alert spam)
- Auto-resolve when condition clears

**Alert Rules Config:**
```yaml
alerts:
  - name: high_drawdown
    metric: njord_strategy_drawdown_pct
    condition: "> 10.0"
    duration: 60  # seconds
    labels:
      severity: critical
    annotations:
      summary: "Strategy {{ $labels.strategy_id }} drawdown exceeded 10%"

  - name: event_loop_lag
    metric: njord_event_loop_lag_seconds
    condition: "> 0.1"
    duration: 30
    labels:
      severity: warning
```

**API:**
```python
class AlertManager:
    def __init__(
        self,
        bus: BusProto,
        rules_path: Path
    ): ...

    async def evaluate_rules(
        self,
        snapshot: MetricSnapshot
    ) -> list[Alert]:
        """Evaluate alert rules against metric.

        Returns:
            List of alerts fired
        """
        pass

    async def fire_alert(
        self,
        alert: Alert
    ) -> None:
        """Fire alert to configured channels."""
        pass

    def deduplicate_alert(
        self,
        alert: Alert
    ) -> bool:
        """Check if alert is duplicate (within time window).

        Returns:
            True if duplicate (skip), False if new
        """
        pass
```

**Files:**
- `telemetry/alerts.py` (180 LOC)
- `config/alerts.yaml` (example alert rules)
- `tests/test_alert_manager.py`

**Acceptance:**
- Alert rules loaded from YAML
- Threshold conditions evaluated correctly
- Duration requirement enforced (must breach for N seconds)
- Deduplication prevents spam (5 min window)
- Alerts published to `telemetry.alerts` topic
- Test includes threshold breach scenarios
- `make fmt lint type test` green

---

### Phase 9.8 — Metrics Retention & Cleanup 📋
**Status:** Planned
**Dependencies:** 9.7 (Metric Alerts)
**Task:** Implement metrics retention policy and cleanup

**Behavior:**
- Define retention periods per metric type
- Automatically delete old metrics from journal
- Downsample old metrics (1m → 5m → 1h → 1d)
- Compress old journals (gzip)
- Scheduled cleanup task (daily cron)

**Retention Policy:**
```yaml
retention:
  raw_metrics:
    - resolution: 1m
      retention_days: 7
    - resolution: 5m
      retention_days: 30
    - resolution: 1h
      retention_days: 180
    - resolution: 1d
      retention_days: 730  # 2 years

  cleanup_schedule: "0 2 * * *"  # 2 AM daily (cron format)
```

**Note:** Cron schedule validation uses simple regex (stdlib only, no croniter dependency).

**API:**
```python
class MetricsRetention:
    def __init__(
        self,
        journal_dir: Path,
        policy: RetentionPolicy
    ): ...

    def apply_retention(self) -> None:
        """Apply retention policy to metrics journals."""
        pass

    def downsample_metrics(
        self,
        source_resolution: str,
        target_resolution: str,
        cutoff_days: int
    ) -> None:
        """Downsample metrics older than cutoff."""
        pass

    def compress_journals(
        self,
        older_than_days: int
    ) -> None:
        """Compress journals older than threshold."""
        pass

    def delete_expired(
        self,
        older_than_days: int
    ) -> None:
        """Delete metrics older than retention period."""
        pass
```

**Files:**
- `telemetry/retention.py` (150 LOC)
- `scripts/metrics_cleanup.py` (CLI for manual cleanup)
- `tests/test_metrics_retention.py`

**Acceptance:**
- Retention policy correctly identifies old metrics
- Downsampling produces correct aggregates
- Compression reduces disk usage (test with sample data)
- Deletion removes only expired metrics
- Cron schedule parseable (basic format check: 5 space-separated fields, stdlib only, no external deps)
- Test includes retention boundary conditions
- `make fmt lint type test` green

---

### Phase 9.9 — Telemetry Documentation 📋
**Status:** Planned
**Dependencies:** 9.8 (Metrics Retention & Cleanup)
**Task:** Document telemetry system and operational procedures

**Deliverables:**

**1. Metrics Catalog**
- Complete list of all exposed metrics
- Metric types, labels, help text
- Example PromQL queries
- Alert rule examples

**2. Grafana Setup Guide**
- Prometheus installation and configuration
- Grafana installation and datasource setup
- Dashboard import instructions
- Alert channel configuration

**3. Operations Runbook**
- Starting/stopping telemetry services
- Troubleshooting common issues
- Metrics retention management
- Performance tuning (cardinality, scrape interval)

**4. API Documentation**
- MetricSnapshot, StrategyMetrics, SystemMetrics contracts
- PrometheusExporter usage
- Instrumentation decorator usage
- Custom metric registration

**Files:**
- `docs/telemetry/metrics_catalog.md`
- `docs/telemetry/grafana_setup.md`
- `docs/telemetry/operations_runbook.md`
- `docs/telemetry/api_reference.md`
- `tests/test_telemetry_docs.py` (validate links, code examples)

**Acceptance:**
- Metrics catalog complete (all metrics documented)
- Setup guide tested (fresh Grafana installation)
- Runbook covers common scenarios
- API docs include working code examples
- All markdown links valid
- Code examples in docs execute without errors
- `make fmt lint type test` green

---

**Phase 9 Acceptance Criteria:**
- [ ] All 10 tasks completed (9.0-9.9)
- [ ] `make fmt lint type test` green
- [ ] Prometheus exporter serves metrics on `/metrics` endpoint
- [ ] All core services instrumented with metrics
- [ ] Grafana dashboards import and display data
- [ ] Metric aggregation service running and persisting data
- [ ] Performance attribution calculates correctly
- [ ] Real-time dashboard accessible and updating
- [ ] Alert rules fire on threshold violations
- [ ] Metrics retention policy applied automatically
- [ ] Documentation complete and verified
- [ ] No runtime dependencies beyond existing stack (Prometheus/Grafana deployment-only)
- [ ] Metric cardinality bounded (warn at 100 unique label combinations)
- [ ] Performance overhead <1% (benchmark test)

---

## Integration with Existing System

### Telemetry Flow
```
Services (risk_engine, paper_trader, broker, strategies)
    ↓
Emit MetricSnapshot to telemetry.metrics topic
    ↓
MetricAggregator (9.4) — Aggregate & Persist
    ↓
PrometheusExporter (9.1) — Serve /metrics endpoint
    ↓
Prometheus (external) — Scrape metrics
    ↓
Grafana (external) — Visualize dashboards
    ↓
AlertManager (9.7) — Fire alerts on thresholds
    ↓
Operators — Monitor & respond
```

### Example Telemetry Session
```bash
# 1. Start metric aggregator
python -m apps.metric_aggregator --config ./config/base.yaml

# 2. Start Prometheus exporter
python -m telemetry.prometheus --port 9090

# 3. Configure Prometheus to scrape
cat > prometheus.yml <<EOF
scrape_configs:
  - job_name: 'njord'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 5s
EOF

# 4. Start Prometheus
prometheus --config.file=prometheus.yml

# 5. Import Grafana dashboards
grafana-cli admin reset-admin-password admin
# Import deploy/grafana/*.json via UI

# 6. Start real-time dashboard (optional)
python -m apps.metrics_dashboard --port 8080

# 7. View metrics
curl http://localhost:9090/metrics
open http://localhost:3000  # Grafana
open http://localhost:8080  # Real-time dashboard
```

---

## Dependencies Summary

```
Phase 8 (Execution Layer) ✅
    └─> Phase 9.0 (Metrics Contracts)
            └─> 9.1 (Prometheus Exporter)
                    └─> 9.2 (Service Instrumentation)
                            └─> 9.3 (Grafana Dashboards)
                                    └─> 9.4 (Metric Aggregator)
                                            └─> 9.5 (Performance Attribution)
                                                    └─> 9.6 (Real-Time Dashboard)
                                                            └─> 9.7 (Metric Alerts)
                                                                    └─> 9.8 (Metrics Retention)
                                                                            └─> 9.9 (Telemetry Docs)
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---
