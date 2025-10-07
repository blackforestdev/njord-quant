# Grafana Dashboards for Njord Quant

This directory contains Grafana dashboard configurations for comprehensive monitoring and visualization of the Njord Quant trading system.

## Dashboard Overview

| Dashboard | Description | Metrics |
|-----------|-------------|---------|
| **system_health.json** | System-level health monitoring | Event loop lag, bus throughput, memory usage, journal writes, subscriptions |
| **trading_activity.json** | Real-time trading operations | Orders, fills, rejections, positions, PnL, fill latency |
| **strategy_performance.json** | Strategy performance analytics | Equity curves, Sharpe ratios, win rates, drawdowns, signals |
| **execution_quality.json** | Execution quality metrics | Slippage, implementation shortfall, venue fill rates, order sizes |

## Prerequisites

1. **Prometheus** — Running and scraping metrics from Njord services
   - Default: `http://localhost:9090`
   - Metrics endpoint: `http://localhost:9090/metrics` (from PrometheusExporter)

2. **Grafana** — Version 8.0 or higher
   - Download: https://grafana.com/grafana/download
   - Docker: `docker run -d -p 3000:3000 grafana/grafana-oss`

## Setup Instructions

### Option 1: Automated Setup (Provisioning)

For production deployments, use Grafana's provisioning system:

1. **Copy datasources config**:
   ```bash
   sudo cp datasources.yaml /etc/grafana/provisioning/datasources/
   ```

2. **Copy dashboard configs**:
   ```bash
   sudo cp *.json /etc/grafana/provisioning/dashboards/
   ```

3. **Restart Grafana**:
   ```bash
   sudo systemctl restart grafana-server
   ```

Grafana will automatically load the datasources and dashboards on startup.

### Option 2: Manual Import (Development/Testing)

1. **Access Grafana UI**:
   - Open browser to `http://localhost:3000`
   - Default credentials: `admin` / `admin` (change on first login)

2. **Configure Prometheus Datasource**:
   - Navigate to: **Configuration** → **Data Sources** → **Add data source**
   - Select: **Prometheus**
   - Set URL: `http://localhost:9090` (or your Prometheus address)
   - Click: **Save & Test**
   - Or use the provided `datasources.yaml`:
     - Navigate to: **Configuration** → **Data Sources** → **Settings** (gear icon)
     - Import from YAML

3. **Import Dashboards**:

   **Method A: Via UI**
   - Navigate to: **Create** (+) → **Import**
   - Click: **Upload JSON file**
   - Select a dashboard file (e.g., `system_health.json`)
   - Select datasource: **Prometheus**
   - Click: **Import**
   - Repeat for each dashboard

   **Method B: Via API**
   ```bash
   # Set Grafana credentials
   export GRAFANA_URL="http://localhost:3000"
   export GRAFANA_USER="admin"
   export GRAFANA_PASS="admin"

   # Import each dashboard
   for dashboard in *.json; do
     curl -X POST -H "Content-Type: application/json" \
       -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
       -d @"${dashboard}" \
       "${GRAFANA_URL}/api/dashboards/db"
   done
   ```

## Dashboard Usage

### System Health Dashboard

**Purpose**: Monitor system-level metrics for operational health.

**Key Panels**:
- **Event Loop Lag**: Detects async event loop delays (alert if >100ms)
- **Bus Message Throughput**: Message pub/sub rates across Redis topics
- **Memory Usage by Service**: Track memory consumption per service
- **Journal Write Rate**: Persistence operation frequency
- **Active Subscriptions**: Number of active topic subscriptions

**Variables**:
- `service`: Filter by service name (All / risk_engine / paper_trader / broker / etc.)

**Refresh**: Auto-refresh every 5 seconds

---

### Trading Activity Dashboard

**Purpose**: Real-time view of trading operations and order flow.

**Key Panels**:
- **Order Activity Rate**: Orders placed vs filled vs rejected
- **Risk Rejection Reasons**: Bar/pie chart of denial reasons
- **Position Sizes by Strategy**: Current positions per strategy and symbol
- **Daily PnL by Strategy**: Stacked bar chart of daily profits/losses
- **Fill Latency Distribution**: P50/P95/P99 latency heatmap
- **Open Orders**: Current count of open orders

**Variables**:
- `strategy`: Filter by strategy ID
- `symbol`: Filter by trading symbol
- `venue`: Filter by exchange venue

**Refresh**: Auto-refresh every 5 seconds

---

### Strategy Performance Dashboard

**Purpose**: Analyze strategy performance and risk-adjusted returns.

**Key Panels**:
- **Equity Curves**: Multi-strategy PnL overlay for comparison
- **Sharpe Ratio Comparison**: Bar gauge of risk-adjusted returns
- **Win Rate by Strategy**: Gauge showing win/loss percentage
- **Max Drawdown by Strategy**: Worst peak-to-trough decline
- **Signal Generation Rate**: Rate of signals emitted per strategy
- **Signal Generation Duration**: Latency heatmap
- **Strategy Error Rate**: Errors/exceptions per strategy

**Variables**:
- `strategy`: Filter by strategy ID

**Refresh**: Auto-refresh every 5 seconds
**Time Range**: Default 6 hours (adjustable)

---

### Execution Quality Dashboard

**Purpose**: Monitor execution quality, slippage, and venue performance.

**Key Panels**:
- **Execution Slippage by Algorithm**: Slippage in bps (TWAP/VWAP/Iceberg/POV)
- **Fill Price Deviation Distribution**: Deviation from reference price
- **Implementation Shortfall Distribution**: Heatmap of execution costs
- **Venue Fill Rate**: Percentage of orders filled per venue
- **Order Size Distribution**: Heatmap of order sizes in USD
- **Execution Completion Rate**: Percentage of orders fully executed
- **Total Fills by Venue**: Bar gauge of venue activity
- **Risk Check Latency**: P95 latency of risk engine processing

**Variables**:
- `algo`: Filter by algorithm type (TWAP/VWAP/Iceberg/POV)
- `symbol`: Filter by trading symbol
- `venue`: Filter by exchange venue
- `strategy`: Filter by strategy ID

**Refresh**: Auto-refresh every 5 seconds

## Alerting

### Recommended Alert Rules

Configure alerts in Grafana for critical thresholds:

1. **Event Loop Lag > 100ms**
   - Query: `njord_event_loop_lag_seconds > 0.1`
   - Severity: Warning

2. **Strategy Drawdown > 10%**
   - Query: `njord_strategy_max_drawdown_pct < -10`
   - Severity: Critical

3. **Risk Rejections Spike**
   - Query: `rate(njord_intents_denied_total[5m]) > 10`
   - Severity: Warning

4. **Fill Rate < 95%**
   - Query: `njord_fills_generated_total / njord_orders_placed_total < 0.95`
   - Severity: Warning

5. **Kill-Switch Triggered**
   - Query: `njord_killswitch_trips_total > 0`
   - Severity: Critical

### Configuring Alerts

1. Navigate to dashboard panel
2. Click panel title → **Edit**
3. Select **Alert** tab
4. Click **Create Alert**
5. Set conditions and thresholds
6. Configure notification channels (email, Slack, PagerDuty, etc.)

## Troubleshooting

### Dashboards show "No Data"

**Causes**:
- Prometheus not scraping metrics
- `NJORD_ENABLE_METRICS=1` not set
- Services not emitting metrics
- Incorrect Prometheus URL in datasource

**Solutions**:
```bash
# Check Prometheus is running
curl http://localhost:9090/api/v1/status/config

# Check metrics endpoint is accessible
curl http://localhost:9090/metrics | grep njord

# Verify env var is set
export NJORD_ENABLE_METRICS=1

# Check service logs for metric emission
tail -f logs/journal/risk_engine.log | grep telemetry
```

### Panels show errors

**Check datasource**:
- Navigate to: **Configuration** → **Data Sources** → **Prometheus**
- Click: **Save & Test**
- Ensure status is: "Data source is working"

**Check metric names**:
- Some panels query metrics not yet implemented (e.g., `njord_strategy_sharpe_ratio`)
- These will be populated as Phase 9.4-9.9 are implemented
- Safe to ignore for now

### Slow dashboard performance

**Reduce query interval**:
- Change `[1m]` to `[5m]` in rate() queries
- Increase scrape interval in Prometheus config
- Reduce time range (e.g., from 6h to 1h)

**Optimize queries**:
- Add label filters to reduce cardinality
- Use recording rules in Prometheus for expensive queries

## Customization

### Adding Custom Panels

1. Open dashboard in edit mode
2. Click **Add panel** → **Add new panel**
3. Configure query in PromQL:
   ```promql
   # Example: Total intents by strategy
   sum by (strategy_id) (njord_intents_received_total)
   ```
4. Select visualization type (Time series, Gauge, Bar chart, etc.)
5. Configure display options (legend, thresholds, colors)
6. Click **Apply**

### Creating Dashboard Folders

Organize dashboards into folders:

1. Navigate to: **Dashboards** → **Browse**
2. Click: **New Folder**
3. Name: "Njord Quant"
4. Move dashboards into folder

### Exporting Dashboards

To save modified dashboards:

1. Navigate to dashboard
2. Click: **Settings** (gear icon) → **JSON Model**
3. Copy JSON
4. Save to `.json` file in this directory

## Integration with Phase 9.4+

### Metric Aggregation Service (Phase 9.4)

Once implemented, dashboards will automatically reflect:
- Aggregated rollups (1m → 5m → 1h → 1d)
- Downsampled historical data
- Reduced query load on Prometheus

### Real-Time Dashboard (Phase 9.6)

Alternative to Grafana for lightweight monitoring:
- Embedded HTML/JS dashboard
- WebSocket/SSE streaming
- Access at: `http://localhost:8080`

Both can coexist — use Grafana for detailed analysis, real-time dashboard for quick checks.

## Support

For issues or feature requests:
- Check: `ROADMAP.md` → Phase 9 status
- Review: `telemetry/` module documentation
- Contact: Njord Trust team

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-07 | Initial dashboard configs for Phase 9.3 |

---

**Maintained By**: Njord Trust
**License**: Proprietary
