# Grafana Setup Guide

Step-by-step guide to setting up Prometheus and Grafana for Njord Quant telemetry.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Prometheus Installation](#prometheus-installation)
- [Grafana Installation](#grafana-installation)
- [Datasource Configuration](#datasource-configuration)
- [Dashboard Import](#dashboard-import)
- [Alert Channel Configuration](#alert-channel-configuration)
- [Verification](#verification)

---

## Prerequisites

- Docker and Docker Compose installed
- Njord Quant telemetry services running
- Ports 9090 (Prometheus) and 3000 (Grafana) available

---

## Prometheus Installation

### Using Docker Compose

1. Create `docker-compose.telemetry.yml`:

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: njord_prometheus
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./deploy/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: njord_grafana
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./deploy/grafana/provisioning:/etc/grafana/provisioning:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=changeme
      - GF_USERS_ALLOW_SIGN_UP=false
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

2. Create Prometheus configuration `deploy/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'njord_quant'
    static_configs:
      - targets: ['host.docker.internal:9091']
        labels:
          instance: 'njord_quant'
          environment: 'production'

  - job_name: 'njord_metrics_dashboard'
    static_configs:
      - targets: ['host.docker.internal:8080']
        labels:
          instance: 'metrics_dashboard'
```

3. Start services:

```bash
docker-compose -f docker-compose.telemetry.yml up -d
```

4. Verify Prometheus is running:

```bash
curl http://localhost:9090/-/healthy
# Expected: Prometheus is Healthy.
```

### Manual Installation (Linux)

```bash
# Download Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz

# Extract
tar xvfz prometheus-2.45.0.linux-amd64.tar.gz
cd prometheus-2.45.0.linux-amd64

# Copy config
cp deploy/prometheus/prometheus.yml ./

# Start Prometheus
./prometheus --config.file=prometheus.yml
```

---

## Grafana Installation

### Using Docker (Recommended)

Already configured in docker-compose above. Access at: http://localhost:3000

**Default credentials:**
- Username: `admin`
- Password: `changeme` (change this!)

### Manual Installation (Linux)

```bash
# Add Grafana repository
sudo apt-get install -y software-properties-common
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -

# Install
sudo apt-get update
sudo apt-get install grafana

# Start service
sudo systemctl start grafana-server
sudo systemctl enable grafana-server
```

---

## Datasource Configuration

### Via Provisioning (Recommended)

1. Create `deploy/grafana/provisioning/datasources/prometheus.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 15s
```

2. Restart Grafana:

```bash
docker-compose -f docker-compose.telemetry.yml restart grafana
```

### Via UI

1. Log in to Grafana (http://localhost:3000)
2. Navigate to **Configuration** → **Data Sources**
3. Click **Add data source**
4. Select **Prometheus**
5. Configure:
   - **Name:** Prometheus
   - **URL:** http://prometheus:9090 (Docker) or http://localhost:9090 (local)
   - **Access:** Server (default)
6. Click **Save & Test**

---

## Dashboard Import

### Via Provisioning (Recommended)

1. Create `deploy/grafana/provisioning/dashboards/dashboards.yml`:

```yaml
apiVersion: 1

providers:
  - name: 'Njord Quant'
    orgId: 1
    folder: 'Njord Quant'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

2. Copy dashboard JSON files:

```bash
cp deploy/grafana/*.json deploy/grafana/provisioning/dashboards/
```

3. Restart Grafana:

```bash
docker-compose -f docker-compose.telemetry.yml restart grafana
```

### Via UI

1. Log in to Grafana
2. Navigate to **Dashboards** → **Browse**
3. Click **Import**
4. Upload dashboard JSON files from `deploy/grafana/`:
   - `system_health.json`
   - `trading_activity.json`
   - `strategy_performance.json`
   - `execution_quality.json`

5. Select **Prometheus** as datasource
6. Click **Import**

---

## Alert Channel Configuration

### Webhook Notification Channel

1. Navigate to **Alerting** → **Notification channels**
2. Click **Add channel**
3. Configure:
   - **Name:** Njord Alerts
   - **Type:** Webhook
   - **URL:** http://host.docker.internal:8080/api/alerts
   - **HTTP Method:** POST
4. Click **Send Test** to verify
5. Click **Save**

### Log File Notification Channel

1. Click **Add channel**
2. Configure:
   - **Name:** Alert Logs
   - **Type:** DingDing/Webhook/etc (use file output if available)
3. Click **Save**

### Configuring Dashboard Alerts

Alerts are pre-configured in the imported dashboards. To modify:

1. Open dashboard (e.g., "System Health")
2. Click panel title → **Edit**
3. Navigate to **Alert** tab
4. Modify conditions as needed
5. Add notification channels
6. Click **Save**

---

## Verification

### 1. Check Prometheus Targets

```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job, health}'
```

Expected output:
```json
{
  "job": "njord_quant",
  "health": "up"
}
```

### 2. Query Metrics

```bash
curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=njord_strategy_pnl_usd' | jq
```

### 3. Verify Grafana Dashboards

1. Open http://localhost:3000
2. Navigate to **Dashboards** → **Browse**
3. Verify all 4 dashboards are imported:
   - System Health
   - Trading Activity
   - Strategy Performance
   - Execution Quality

4. Open each dashboard and verify:
   - Data is loading
   - All panels display metrics
   - Time range selector works
   - Variables (strategy, symbol) populate

### 4. Test Alerts

**Trigger a test alert:**

```python
# In Python shell or test script
from telemetry.registry import MetricRegistry
import asyncio

async def trigger_alert():
    registry = MetricRegistry()

    # Register and set metric that exceeds threshold
    gauge = await registry.register_gauge(
        "njord_event_loop_lag_seconds",
        "Event loop lag"
    )
    gauge.set(0.5, None)  # Exceeds 0.1 threshold

    # Wait for alert to fire
    await asyncio.sleep(60)

asyncio.run(trigger_alert())
```

**Verify alert in Grafana:**
1. Navigate to **Alerting** → **Alert Rules**
2. Check for "HighEventLoopLag" in alerting state
3. Verify notification sent to configured channels

---

## Troubleshooting

### Prometheus Not Scraping Metrics

**Symptoms:** "No data" in Grafana dashboards

**Solutions:**
1. Check Prometheus targets: http://localhost:9090/targets
2. Verify njord services are running:
   ```bash
   curl http://localhost:9091/metrics
   ```
3. Check Docker network connectivity:
   ```bash
   docker exec njord_prometheus ping host.docker.internal
   ```
4. Review Prometheus logs:
   ```bash
   docker logs njord_prometheus
   ```

### Dashboards Show "N/A"

**Solutions:**
1. Verify datasource connection in Grafana settings
2. Check metric names match in queries (case-sensitive)
3. Verify time range includes data
4. Check Prometheus query in Explore tab

### Alerts Not Firing

**Solutions:**
1. Check alert rule configuration in dashboard
2. Verify notification channel is configured
3. Review Grafana alert logs:
   ```bash
   docker logs njord_grafana | grep alert
   ```
4. Test notification channel manually

### High Memory Usage

**Solutions:**
1. Reduce scrape interval in `prometheus.yml`
2. Decrease retention period:
   ```yaml
   command:
     - '--storage.tsdb.retention.time=7d'
   ```
3. Add recording rules for frequently queried metrics

---

## Production Deployment

### Security Hardening

1. **Change default passwords:**
   ```bash
   docker exec -it njord_grafana grafana-cli admin reset-admin-password <newpassword>
   ```

2. **Enable HTTPS:**
   - Configure reverse proxy (nginx/traefik)
   - Use Let's Encrypt for SSL certificates

3. **Restrict network access:**
   ```yaml
   # docker-compose.telemetry.yml
   ports:
     - "127.0.0.1:3000:3000"  # Grafana localhost only
     - "127.0.0.1:9090:9090"  # Prometheus localhost only
   ```

4. **Enable authentication on Prometheus:**
   ```yaml
   # prometheus.yml
   basic_auth_users:
     prometheus: <bcrypt_hash>
   ```

### Backup Configuration

```bash
# Backup Grafana dashboards
docker exec njord_grafana grafana-cli admin export-dashboards > dashboards_backup.json

# Backup Prometheus data
docker run --rm -v prometheus_data:/data -v $(pwd):/backup \
  busybox tar czf /backup/prometheus_backup.tar.gz /data
```

---

## Next Steps

- Review [Metrics Catalog](./metrics_catalog.md) for available metrics
- Configure custom dashboards for your use case
- Set up [Alert Rules](./metrics_catalog.md#alert-rule-examples)
- Read [Operations Runbook](./operations_runbook.md) for maintenance procedures

---

**Last Updated:** 2025-10-07
**Maintainer:** Njord Trust
**Support:** See [Operations Runbook](./operations_runbook.md) for troubleshooting
