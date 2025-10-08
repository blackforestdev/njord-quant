# Telemetry Operations Runbook

Operational procedures for Njord Quant telemetry system.

## Table of Contents

- [Service Management](#service-management)
- [Metrics Retention Management](#metrics-retention-management)
- [Troubleshooting](#troubleshooting)
- [Performance Tuning](#performance-tuning)
- [Maintenance Procedures](#maintenance-procedures)
- [Incident Response](#incident-response)

---

## Service Management

### Starting Telemetry Services

```bash
# 1. Start Prometheus exporter
python -m telemetry.prometheus --port 9091 --config-root config/

# 2. Start metrics dashboard
python -m apps.metrics_dashboard.main --port 8080

# 3. Start metric aggregator (if using)
python -m telemetry.aggregator --config-root config/

# 4. Start Prometheus/Grafana (Docker)
docker-compose -f docker-compose.telemetry.yml up -d
```

### Stopping Telemetry Services

```bash
# Graceful shutdown
docker-compose -f docker-compose.telemetry.yml down

# Stop individual services
pkill -f "telemetry.prometheus"
pkill -f "metrics_dashboard"
```

### Service Health Checks

```bash
# Check Prometheus exporter
curl http://localhost:9091/metrics | head -20

# Check metrics dashboard
curl http://localhost:8080/

# Check Prometheus
curl http://localhost:9090/-/healthy

# Check Grafana
curl http://localhost:3000/api/health
```

### Service Logs

```bash
# View Prometheus exporter logs
journalctl -u njord-prometheus-exporter -f

# View metrics dashboard logs
journalctl -u njord-dashboard -f

# Docker logs
docker logs njord_prometheus -f
docker logs njord_grafana -f
```

---

## Metrics Retention Management

### Manual Cleanup

```bash
# Run metrics cleanup script
python scripts/metrics_cleanup.py \
  --journal-dir data/journals \
  --config-root config \
  --verbose

# Dry run (preview changes)
python scripts/metrics_cleanup.py --dry-run
```

### Automated Cleanup (Cron)

```bash
# Add to crontab
crontab -e

# Run cleanup daily at 2 AM
0 2 * * * cd /opt/njord_quant && python scripts/metrics_cleanup.py --journal-dir data/journals
```

### Monitoring Disk Usage

```bash
# Check journal directory size
du -sh data/journals/

# Find largest journal files
find data/journals -type f -exec du -h {} \; | sort -rh | head -10

# Check compressed vs uncompressed
find data/journals -name "*.jsonl" -exec du -ch {} + | tail -1
find data/journals -name "*.jsonl.gz" -exec du -ch {} + | tail -1
```

### Adjusting Retention Policy

Edit `config/base.yaml`:

```yaml
retention:
  raw_metrics:
    - resolution: 1m
      retention_days: 7     # Reduce from 7 to 3 days
    - resolution: 5m
      retention_days: 30
    - resolution: 1h
      retention_days: 180
    - resolution: 1d
      retention_days: 730

  cleanup_schedule: "0 2 * * *"  # Daily at 2 AM
```

Apply changes:
```bash
python scripts/metrics_cleanup.py --config-root config
```

---

## Troubleshooting

### High Cardinality Warnings

**Symptoms:**
```
WARNING telemetry.metric_cardinality_high metric_name=njord_orders_total unique_combinations=150
```

**Solutions:**

1. **Identify high-cardinality labels:**
   ```bash
   # Query Prometheus
   curl -G http://localhost:9090/api/v1/label/__name__/values | jq
   ```

2. **Review metric usage:**
   ```python
   from telemetry.contracts import MetricSnapshot

   # Check label combinations
   print(MetricSnapshot._label_combinations)
   ```

3. **Reduce cardinality:**
   - Remove unique IDs from labels
   - Use label aggregation
   - Implement sampling for high-frequency metrics

### Memory Issues

**Symptoms:**
- `njord_memory_usage_mb > 512`
- OOM kills
- Slow query performance

**Solutions:**

1. **Check current memory:**
   ```bash
   ps aux | grep python | awk '{print $6/1024 " MB\t" $11}'
   ```

2. **Reduce metric retention:**
   ```bash
   # Immediate cleanup
   python scripts/metrics_cleanup.py --journal-dir data/journals
   ```

3. **Optimize Prometheus:**
   ```yaml
   # docker-compose.telemetry.yml
   command:
     - '--storage.tsdb.retention.time=7d'
     - '--storage.tsdb.retention.size=10GB'
   ```

4. **Enable compression earlier:**
   ```python
   # In config
   retention.compress_journals(older_than_days=1)  # Compress after 1 day
   ```

### Event Loop Lag

**Symptoms:**
- `njord_event_loop_lag_seconds > 0.1`
- Slow metric updates
- Dashboard delays

**Solutions:**

1. **Check system load:**
   ```bash
   top -p $(pgrep -f njord)
   ```

2. **Reduce scrape frequency:**
   ```yaml
   # prometheus.yml
   scrape_configs:
     - job_name: 'njord_quant'
       scrape_interval: 30s  # Increase from 15s
   ```

3. **Optimize metric aggregation:**
   ```python
   # Batch metric updates
   await aggregator.flush_metrics_batch(batch_size=100)
   ```

### Missing Metrics

**Symptoms:**
- Dashboards show "No Data"
- Prometheus shows no targets

**Solutions:**

1. **Verify service is running:**
   ```bash
   curl http://localhost:9091/metrics
   ```

2. **Check Prometheus scrape status:**
   ```bash
   curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job, health, lastError}'
   ```

3. **Verify network connectivity:**
   ```bash
   # From Prometheus container
   docker exec njord_prometheus wget -O- http://host.docker.internal:9091/metrics
   ```

4. **Check firewall rules:**
   ```bash
   sudo ufw status
   sudo iptables -L -n | grep 9091
   ```

### Alert Not Firing

**Symptoms:**
- Metric exceeds threshold but no alert
- Alert shows in "Pending" state

**Solutions:**

1. **Check alert rule:**
   ```bash
   curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name=="HighDrawdown")'
   ```

2. **Verify evaluation:**
   ```bash
   # Check if condition is true
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=njord_strategy_drawdown_pct > 10.0'
   ```

3. **Check duration:**
   - Alert must stay above threshold for specified duration
   - Review `for: 1m` clause in alert rule

4. **Verify notification channel:**
   - Test notification channel in Grafana
   - Check webhook endpoint is reachable

---

## Performance Tuning

### Cardinality Management

**Best Practices:**

1. **Limit label values:**
   ```python
   # Good: Bounded set
   labels = {"strategy_id": "alpha", "venue": "binance"}

   # Bad: Unbounded set
   labels = {"order_id": "uuid-12345"}  # Don't use unique IDs
   ```

2. **Use recording rules:**
   ```yaml
   # prometheus_rules.yml
   groups:
     - name: aggregations
       interval: 30s
       rules:
         - record: njord:strategy_pnl:sum
           expr: sum by (strategy_id) (njord_strategy_pnl_usd)
   ```

3. **Monitor cardinality:**
   ```bash
   # Query series count
   curl http://localhost:9090/api/v1/status/tsdb | jq '.data.seriesCountByMetricName'
   ```

### Scrape Interval Optimization

**Guidelines:**

| Metric Type | Recommended Interval |
|-------------|---------------------|
| Fast-changing (fills, orders) | 5-15s |
| Slow-changing (P&L, positions) | 30-60s |
| System health | 15-30s |
| Historical aggregates | 5m-1h |

**Configure in prometheus.yml:**
```yaml
scrape_configs:
  - job_name: 'njord_quant_fast'
    scrape_interval: 5s
    static_configs:
      - targets: ['localhost:9091']

  - job_name: 'njord_quant_slow'
    scrape_interval: 60s
    static_configs:
      - targets: ['localhost:9091']
```

### Query Optimization

**Use recording rules for expensive queries:**

```yaml
# prometheus_rules.yml
groups:
  - name: performance
    interval: 1m
    rules:
      # Pre-calculate fill rate
      - record: njord:fills:rate1m
        expr: rate(njord_fills_generated_total[1m])

      # Pre-calculate P&L by strategy
      - record: njord:strategy_pnl:by_strategy
        expr: sum by (strategy_id) (njord_strategy_pnl_usd)
```

**Use in Grafana:**
```promql
# Instead of: rate(njord_fills_generated_total[1m])
# Use: njord:fills:rate1m
```

---

## Maintenance Procedures

### Weekly Maintenance

```bash
# 1. Check disk usage
df -h data/journals/

# 2. Review metric cardinality
curl http://localhost:9090/api/v1/status/tsdb | jq

# 3. Verify all dashboards loading
curl http://localhost:3000/api/dashboards/home

# 4. Review alert history
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'
```

### Monthly Maintenance

```bash
# 1. Update Prometheus/Grafana
docker-compose -f docker-compose.telemetry.yml pull
docker-compose -f docker-compose.telemetry.yml up -d

# 2. Backup Grafana dashboards
docker exec njord_grafana grafana-cli admin export-dashboards > dashboards_backup.json

# 3. Backup Prometheus data
docker run --rm -v prometheus_data:/data -v $(pwd):/backup \
  busybox tar czf /backup/prometheus_$(date +%Y%m%d).tar.gz /data

# 4. Review and rotate logs
journalctl --vacuum-time=30d
```

### Quarterly Maintenance

```bash
# 1. Review retention policy effectiveness
python scripts/metrics_cleanup.py --dry-run --verbose

# 2. Analyze query performance
# In Prometheus UI: Status > Query Log

# 3. Update alert thresholds based on historical data
# Review P95/P99 values for key metrics

# 4. Audit metric usage
# Identify and remove unused metrics
```

---

## Incident Response

### High Drawdown Alert

1. **Immediate actions:**
   ```bash
   # Check current P&L
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=njord_strategy_pnl_usd' | jq

   # Activate kill-switch if needed
   python scripts/njord_kill.py --activate
   ```

2. **Investigation:**
   - Review strategy performance dashboard
   - Check recent fills and orders
   - Analyze market conditions

3. **Mitigation:**
   - Reduce position sizes
   - Disable underperforming strategies
   - Adjust risk limits

### System Health Degradation

1. **Immediate actions:**
   ```bash
   # Check system metrics
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=njord_event_loop_lag_seconds'

   # Check memory
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=njord_memory_usage_mb'
   ```

2. **Investigation:**
   - Review system health dashboard
   - Check for metric storms (high cardinality)
   - Analyze bus message rates

3. **Mitigation:**
   - Restart affected services
   - Reduce scrape frequency
   - Clean up old metrics

### Data Loss

1. **Immediate actions:**
   ```bash
   # Stop writes
   pkill -f "telemetry.prometheus"

   # Check last backup
   ls -lh prometheus_backup_*.tar.gz | tail -1
   ```

2. **Recovery:**
   ```bash
   # Restore from backup
   docker-compose -f docker-compose.telemetry.yml down
   docker run --rm -v prometheus_data:/data -v $(pwd):/backup \
     busybox tar xzf /backup/prometheus_20251007.tar.gz -C /data
   docker-compose -f docker-compose.telemetry.yml up -d
   ```

3. **Verification:**
   ```bash
   # Verify data restored
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=njord_strategy_pnl_usd[1h]'
   ```

---

## Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| On-call Engineer | [TBD] | Primary |
| System Admin | [TBD] | Secondary |
| Product Owner | [TBD] | Business impact |

---

## References

- [Metrics Catalog](./metrics_catalog.md) - All available metrics
- [Grafana Setup](./grafana_setup.md) - Installation and configuration
- [API Reference](./api_reference.md) - Programmatic access
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)

---

**Last Updated:** 2025-10-07
**Maintainer:** Njord Trust
**Review Cycle:** Quarterly
