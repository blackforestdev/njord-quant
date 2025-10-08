# Telemetry API Reference

Programmatic reference for Njord Quant telemetry system.

## Table of Contents

- [Contracts](#contracts)
- [Metric Registry](#metric-registry)
- [Prometheus Exporter](#prometheus-exporter)
- [Instrumentation](#instrumentation)
- [Alert Manager](#alert-manager)
- [Metrics Retention](#metrics-retention)
- [Performance Attribution](#performance-attribution)

---

## Contracts

### MetricSnapshot

Immutable metric measurement.

```python
from telemetry.contracts import MetricSnapshot

# Create metric snapshot
snapshot = MetricSnapshot(
    name="njord_strategy_pnl_usd",
    value=1250.50,
    timestamp_ns=1696700000000000000,
    labels={"strategy_id": "alpha"},
    metric_type="gauge"
)

# Serialize
data = snapshot.to_dict()

# Deserialize
snapshot = MetricSnapshot.from_dict(data)
```

**Validation:**
- `name` must not be empty
- `timestamp_ns` must be >= 0
- `labels` must have <= 20 keys
- `metric_type` must be one of: counter, gauge, histogram, summary

### StrategyMetrics

Strategy performance metrics.

```python
from telemetry.contracts import StrategyMetrics

metrics = StrategyMetrics(
    strategy_id="alpha",
    timestamp_ns=1696700000000000000,
    active_positions=5,
    total_pnl=12500.00,
    daily_pnl=450.00,
    win_rate=0.65,
    sharpe_ratio=1.8,
    max_drawdown_pct=8.5,
    orders_sent=120,
    orders_filled=115,
    orders_rejected=5
)

# Validation enforced
assert 0.0 <= metrics.win_rate <= 1.0
assert 0.0 <= metrics.max_drawdown_pct <= 100.0
assert metrics.active_positions >= 0
```

### SystemMetrics

System health metrics.

```python
from telemetry.contracts import SystemMetrics

metrics = SystemMetrics(
    timestamp_ns=1696700000000000000,
    bus_messages_sent=15000,
    bus_messages_received=14500,
    journal_writes=2500,
    journal_bytes=1048576,
    active_subscriptions=8,
    event_loop_lag_ms=15.5,
    memory_usage_mb=256.0
)
```

### Alert

Alert triggered by threshold violation.

```python
from telemetry.contracts import Alert

alert = Alert(
    name="high_drawdown",
    metric_name="njord_strategy_drawdown_pct",
    condition="> 10.0",
    current_value=12.5,
    timestamp_ns=1696700000000000000,
    labels={"severity": "critical", "strategy_id": "alpha"},
    annotations={"summary": "Strategy alpha drawdown exceeded 10%"},
    state="firing",
    duration_sec=60
)
```

### RetentionPolicy

Metrics retention configuration.

```python
from telemetry.contracts import RetentionPolicy, RetentionLevel

policy = RetentionPolicy(
    raw_metrics=(
        RetentionLevel("1m", 7),
        RetentionLevel("5m", 30),
        RetentionLevel("1h", 180),
        RetentionLevel("1d", 730),
    ),
    cleanup_schedule="0 2 * * *"
)

# Validates cron schedule format
assert len(policy.cleanup_schedule.split()) == 5
```

---

## Metric Registry

Thread-safe metric registration and access.

### Basic Usage

```python
from telemetry.registry import MetricRegistry

# Initialize registry
registry = MetricRegistry()

# Register counter
counter = await registry.register_counter(
    name="njord_orders_total",
    help_text="Total orders placed",
    label_names=["strategy_id", "symbol"]
)

# Increment counter
counter.inc(1, {"strategy_id": "alpha", "symbol": "BTC/USDT"})
counter.inc(5, {"strategy_id": "beta", "symbol": "ETH/USDT"})

# Register gauge
gauge = await registry.register_gauge(
    name="njord_strategy_pnl_usd",
    help_text="Strategy P&L in USD",
    label_names=["strategy_id"]
)

# Set gauge value
gauge.set(1250.50, {"strategy_id": "alpha"})
gauge.set(-150.00, {"strategy_id": "beta"})

# Register histogram
histogram = await registry.register_histogram(
    name="njord_fill_latency_ms",
    help_text="Fill latency in milliseconds",
    label_names=["venue"],
    buckets=[10, 50, 100, 500, 1000]
)

# Observe value
histogram.observe(45.5, {"venue": "binance"})
```

### Advanced Usage

```python
# List all metrics
metrics = registry.list_metrics()
for name, metric in metrics.items():
    print(f"{name}: {metric.help_text}")

# Get specific metric
metric = registry.get_metric("njord_orders_total")

# Export for Prometheus
exposition = registry.export_prometheus()
print(exposition)
# Output:
# # HELP njord_orders_total Total orders placed
# # TYPE njord_orders_total counter
# njord_orders_total{strategy_id="alpha",symbol="BTC/USDT"} 1.0
# njord_orders_total{strategy_id="beta",symbol="ETH/USDT"} 5.0
```

---

## Prometheus Exporter

HTTP server exposing metrics endpoint.

### Basic Setup

```python
from telemetry.prometheus import PrometheusExporter
from telemetry.registry import MetricRegistry
from core.bus import Bus

# Initialize
bus = Bus("redis://localhost:6379")
registry = MetricRegistry()

exporter = PrometheusExporter(
    bus=bus,
    port=9091,
    bind_host="127.0.0.1",
    registry=registry
)

# Start server
await exporter.start()

# Server now available at http://localhost:9091/metrics
```

### With Authentication

```python
import os

# Set auth token
os.environ["NJORD_METRICS_TOKEN"] = "secret_token_123"

exporter = PrometheusExporter(
    bus=bus,
    port=9091,
    registry=registry
)

await exporter.start()

# Requires Bearer token:
# curl -H "Authorization: Bearer secret_token_123" http://localhost:9091/metrics
```

### Custom Metrics

```python
# Register custom metrics
gauge = await registry.register_gauge(
    "njord_custom_metric",
    "My custom metric",
    ["label1", "label2"]
)

# Update metric
gauge.set(42.0, {"label1": "value1", "label2": "value2"})

# Metric automatically exported at /metrics endpoint
```

---

## Instrumentation

Automatic metric collection from services.

### Service Instrumentation

```python
from telemetry.instrumentation import instrument_service

# Instrument service automatically
@instrument_service(
    service_name="risk_engine",
    registry=registry,
    bus=bus
)
class RiskEngine:
    async def check_intent(self, intent):
        # Metrics automatically collected:
        # - njord_service_calls_total
        # - njord_service_duration_seconds
        # - njord_service_errors_total
        pass
```

### Manual Instrumentation

```python
from telemetry.instrumentation import record_metric

async def execute_order(order):
    # Start timer
    start_ns = time.time_ns()

    try:
        # Execute order
        result = await broker.place_order(order)

        # Record success
        await record_metric(
            registry,
            "njord_orders_total",
            1.0,
            {"status": "success", "symbol": order.symbol}
        )

        return result

    except Exception as e:
        # Record error
        await record_metric(
            registry,
            "njord_orders_total",
            1.0,
            {"status": "error", "symbol": order.symbol}
        )
        raise

    finally:
        # Record latency
        latency_ms = (time.time_ns() - start_ns) / 1_000_000
        await record_metric(
            registry,
            "njord_order_latency_ms",
            latency_ms,
            {"symbol": order.symbol}
        )
```

---

## Alert Manager

Monitor metrics and fire alerts on threshold violations.

### Basic Setup

```python
from pathlib import Path
from telemetry.alerts import AlertManager
from core.bus import Bus

bus = Bus("redis://localhost:6379")
rules_path = Path("config/alerts.yaml")

# Initialize alert manager
alert_manager = AlertManager(bus=bus, rules_path=rules_path)

# Process metric and check alerts
from telemetry.contracts import MetricSnapshot

snapshot = MetricSnapshot(
    name="njord_strategy_drawdown_pct",
    value=12.5,
    timestamp_ns=int(time.time() * 1_000_000_000),
    labels={"strategy_id": "alpha"},
    metric_type="gauge"
)

# Evaluate rules and fire alerts
await alert_manager.process_metric(snapshot)
```

### Custom Alert Rules

```python
from telemetry.alerts import AlertRule

# Create custom rule
rule = AlertRule(
    name="custom_alert",
    metric="njord_custom_metric",
    condition="> 100.0",
    duration=30,  # seconds
    labels={"severity": "warning"},
    annotations={"summary": "Custom metric exceeded threshold"}
)

# Add to alert manager
alert_manager.rules.append(rule)

# Process metrics
await alert_manager.process_metric(snapshot)
```

### Alert Deduplication

```python
# Alerts are deduplicated within 5-minute window
# Only fires once even if threshold continuously exceeded

for i in range(100):
    snapshot = MetricSnapshot(
        name="njord_event_loop_lag_seconds",
        value=0.5,  # Exceeds threshold
        timestamp_ns=int(time.time() * 1_000_000_000),
        metric_type="gauge"
    )
    await alert_manager.process_metric(snapshot)
    await asyncio.sleep(1)

# Only 1 alert fired (deduplicated)
```

---

## Metrics Retention

Manage disk usage with automatic downsampling and cleanup.

### Basic Usage

```python
from pathlib import Path
from telemetry.retention import MetricsRetention
from telemetry.contracts import RetentionPolicy, RetentionLevel

# Configure retention policy
policy = RetentionPolicy(
    raw_metrics=(
        RetentionLevel("1m", 7),
        RetentionLevel("5m", 30),
        RetentionLevel("1h", 180),
        RetentionLevel("1d", 730),
    ),
    cleanup_schedule="0 2 * * *"
)

# Initialize retention manager
retention = MetricsRetention(
    journal_dir=Path("data/journals"),
    policy=policy
)

# Apply retention policy
stats = retention.apply_retention()
print(f"Downsampled: {stats['downsampled']} files")
print(f"Compressed: {stats['compressed']} files")
print(f"Deleted: {stats['deleted']} files")
```

### Manual Operations

```python
# Downsample specific resolution
downsampled = retention.downsample_metrics(
    source_resolution="1m",
    target_resolution="5m",
    cutoff_days=7
)

# Compress old journals
compressed = retention.compress_journals(older_than_days=7)

# Delete expired metrics
deleted = retention.delete_expired(older_than_days=730)
```

### Cron Schedule Validation

```python
from telemetry.retention import validate_cron_schedule

# Valid schedules
assert validate_cron_schedule("0 2 * * *") is True
assert validate_cron_schedule("*/5 * * * *") is True
assert validate_cron_schedule("0 0,12 * * *") is True

# Invalid schedules
assert validate_cron_schedule("invalid") is False
assert validate_cron_schedule("0 2 *") is False  # Too few fields
```

---

## Performance Attribution

Attribute portfolio performance to strategies.

### Basic Usage

```python
from telemetry.attribution import PerformanceAttribution
from research.data_reader import DataReader

# Initialize
data_reader = DataReader(data_dir=Path("data"))
attribution = PerformanceAttribution(
    data_reader=data_reader,
    portfolio_id="main"
)

# Calculate attribution
report = attribution.calculate_attribution(
    start_ts_ns=1696600000000000000,
    end_ts_ns=1696700000000000000
)

print(f"Portfolio P&L: ${report.portfolio_pnl:,.2f}")
for strategy_id, pnl in report.strategy_pnls.items():
    print(f"  {strategy_id}: ${pnl:,.2f}")
```

### With Benchmark

```python
# Calculate alpha/beta vs benchmark
benchmark_returns = [0.001, 0.002, -0.001, 0.003]  # Daily returns

report = attribution.calculate_attribution(
    start_ts_ns=start_ts,
    end_ts_ns=end_ts,
    benchmark_returns=benchmark_returns
)

print(f"Alpha: {report.alpha:.4f}")
print(f"Beta: {report.beta:.4f}")
print(f"Sharpe Ratio: {report.sharpe_ratio:.2f}")
print(f"Sortino Ratio: {report.sortino_ratio:.2f}")
```

### Brinson Attribution

```python
# Calculate Brinson attribution (allocation + selection effects)
report = attribution.calculate_attribution(
    start_ts_ns=start_ts,
    end_ts_ns=end_ts,
    benchmark_returns=benchmark_returns
)

print("Allocation Effects:")
for strategy_id, effect in report.allocation_effect.items():
    print(f"  {strategy_id}: {effect:.4f}")

print("\nSelection Effects:")
for strategy_id, effect in report.selection_effect.items():
    print(f"  {strategy_id}: {effect:.4f}")
```

---

## Complete Example

Full telemetry setup with all components:

```python
import asyncio
from pathlib import Path
from core.bus import Bus
from telemetry.registry import MetricRegistry
from telemetry.prometheus import PrometheusExporter
from telemetry.alerts import AlertManager
from telemetry.retention import MetricsRetention
from telemetry.contracts import MetricSnapshot, RetentionPolicy, RetentionLevel

async def main():
    # Initialize components
    bus = Bus("redis://localhost:6379")
    registry = MetricRegistry()

    # Start Prometheus exporter
    exporter = PrometheusExporter(
        bus=bus,
        port=9091,
        registry=registry
    )
    await exporter.start()

    # Setup alert manager
    alert_manager = AlertManager(
        bus=bus,
        rules_path=Path("config/alerts.yaml")
    )

    # Setup retention
    policy = RetentionPolicy(
        raw_metrics=(
            RetentionLevel("1m", 7),
            RetentionLevel("5m", 30),
        ),
        cleanup_schedule="0 2 * * *"
    )
    retention = MetricsRetention(
        journal_dir=Path("data/journals"),
        policy=policy
    )

    # Register metrics
    pnl_gauge = await registry.register_gauge(
        "njord_strategy_pnl_usd",
        "Strategy P&L in USD",
        ["strategy_id"]
    )
    orders_counter = await registry.register_counter(
        "njord_orders_total",
        "Total orders placed",
        ["strategy_id"]
    )

    # Emit metrics
    pnl_gauge.set(1250.50, {"strategy_id": "alpha"})
    orders_counter.inc(1, {"strategy_id": "alpha"})

    # Create metric snapshot
    snapshot = MetricSnapshot(
        name="njord_strategy_pnl_usd",
        value=1250.50,
        timestamp_ns=int(time.time() * 1_000_000_000),
        labels={"strategy_id": "alpha"},
        metric_type="gauge"
    )

    # Process with alert manager
    await alert_manager.process_metric(snapshot)

    # Apply retention policy
    stats = retention.apply_retention()
    print(f"Retention applied: {stats}")

    # Metrics available at http://localhost:9091/metrics

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Best Practices

### Metric Naming

```python
# Good: Clear, includes unit
"njord_fill_latency_seconds"
"njord_memory_usage_bytes"
"njord_orders_total"

# Bad: Ambiguous, missing unit
"njord_latency"
"njord_mem"
"njord_orders"
```

### Label Usage

```python
# Good: Bounded cardinality
labels = {
    "strategy_id": "alpha",  # ~10 strategies
    "symbol": "BTC/USDT",    # ~100 symbols
    "venue": "binance"       # ~5 venues
}

# Bad: Unbounded cardinality
labels = {
    "order_id": "uuid-12345",    # Millions of unique values
    "timestamp": "1696700000",   # Infinite values
    "user_ip": "192.168.1.1"    # Too many values
}
```

### Error Handling

```python
try:
    gauge = await registry.register_gauge(
        "njord_metric",
        "Description",
        ["label1"]
    )
    gauge.set(42.0, {"label1": "value"})
except ValueError as e:
    logger.error(f"Metric error: {e}")
    # Handle gracefully, don't crash service
```

---

## References

- [Metrics Catalog](./metrics_catalog.md) - Available metrics
- [Grafana Setup](./grafana_setup.md) - Visualization
- [Operations Runbook](./operations_runbook.md) - Maintenance
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)

---

**Last Updated:** 2025-10-07
**Maintainer:** Njord Trust
**API Version:** 1.0
