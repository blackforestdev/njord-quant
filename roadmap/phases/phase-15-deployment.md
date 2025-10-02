## Phase 15 — Deployment Framework 📋

**Purpose:** Implement production deployment infrastructure with systemd units, configuration management, and operational runbooks.

**Current Status:** Phase 14 complete — Simulation Harness fully operational
**Next Phase:** Phase 16 — Optimization Pass

---

### Phase 15.0 — Systemd Service Templates 📋
**Status:** Planned
**Dependencies:** 14.7 (Simulation Documentation)
**Task:** Create systemd unit files for all long-running services

**Critical Architectural Requirements:**
1. **Service Dependencies:** Correct ordering (Redis → services → strategies)
2. **Restart Policies:** Automatic restart with backoff for transient failures
3. **Resource Limits:** CPU, memory, file descriptor limits enforced
4. **Logging Integration:** Journal forwarding to centralized logs
5. **Security Hardening:** User isolation, capability restrictions, read-only paths

**Deliverables:**

#### 1. Service Unit Template
```ini
# deploy/systemd/njord-md-ingest@.service
[Unit]
Description=Njord Market Data Ingest (%i)
Documentation=https://github.com/njord-trust/njord_quant
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=njord
Group=njord
WorkingDirectory=/opt/njord_quant

# Environment
Environment="PYTHONPATH=/opt/njord_quant"
Environment="NJORD_ENV=production"
EnvironmentFile=/etc/njord/env.conf

# Execution
ExecStartPre=/usr/bin/test -f /opt/njord_quant/config/base.yaml
ExecStart=/opt/njord_quant/venv/bin/python -m apps.md_ingest --symbol %i
ExecReload=/bin/kill -HUP $MAINPID

# Restart policy
Restart=on-failure
RestartSec=5s
StartLimitInterval=300s
StartLimitBurst=5

# Resource limits
MemoryLimit=512M
CPUQuota=100%
TasksMax=100
LimitNOFILE=4096

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/njord_quant/var
ReadOnlyPaths=/opt/njord_quant/config

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=njord-md-ingest-%i

[Install]
WantedBy=multi-user.target
```

#### 2. Service Registry
Create units for all services:
- `njord-md-ingest@.service` (parameterized by symbol)
- `njord-risk-engine.service`
- `njord-paper-trader.service`
- `njord-broker.service` (with live mode guards)
- `njord-portfolio-manager.service`
- `njord-metrics-exporter.service`
- `njord-alert-service.service`
- `njord-audit-service.service`
- `njord-controller.service`

#### 3. Target for Coordinated Start/Stop
```ini
# deploy/systemd/njord.target
[Unit]
Description=Njord Quant Trading System
Documentation=https://github.com/njord-trust/njord_quant
Requires=redis.service
After=redis.service

[Install]
WantedBy=multi-user.target
```

**Files:**
- `deploy/systemd/njord-md-ingest@.service` (~60 lines)
- `deploy/systemd/njord-risk-engine.service` (~65 lines)
- `deploy/systemd/njord-paper-trader.service` (~65 lines)
- `deploy/systemd/njord-broker.service` (~70 lines, includes live mode guards)
- `deploy/systemd/njord-portfolio-manager.service` (~65 lines)
- `deploy/systemd/njord-metrics-exporter.service` (~65 lines)
- `deploy/systemd/njord-alert-service.service` (~65 lines)
- `deploy/systemd/njord-audit-service.service` (~65 lines)
- `deploy/systemd/njord-controller.service` (~65 lines)
- `deploy/systemd/njord.target` (~20 lines)
- `deploy/systemd/README.md` (Installation instructions, ~100 lines)

**Acceptance:**
- All service units include proper dependencies (After=, Requires=)
- Restart policies configured correctly (Restart=on-failure, RestartSec, StartLimitBurst)
- Resource limits enforced (MemoryLimit, CPUQuota, LimitNOFILE)
- Security hardening applied (NoNewPrivileges, ProtectSystem, ReadWritePaths)
- **Test verifies service starts correctly: systemctl --user start njord-risk-engine**
- **Test verifies dependency ordering: risk-engine waits for redis**
- **Test verifies restart policy: service restarts after simulated crash**
- **Test verifies resource limits: MemoryLimit enforced (test with memory spike)**
- Broker service includes ExecStartPre check for NJORD_ENABLE_LIVE guard
- Documentation includes installation and verification steps
- `make fmt lint type test` green (no code changes)

---

### Phase 15.1 — Service Installation Script 📋
**Status:** Planned
**Dependencies:** 15.0 (Systemd Service Templates)
**Task:** Create installation script for deploying services to target host

**Behavior:**
- Install Python dependencies in virtualenv
- Copy service files to /opt/njord_quant
- Install systemd units to /etc/systemd/system
- Create njord user/group with correct permissions
- Set up log directories with proper ownership
- Validate configuration files before enabling services

**API:**
```bash
#!/usr/bin/env bash
# deploy/install.sh

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/njord_quant}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
CONFIG_DIR="${CONFIG_DIR:-/etc/njord}"
LOG_DIR="${LOG_DIR:-/var/log/njord}"
USER="${NJORD_USER:-njord}"
GROUP="${NJORD_GROUP:-njord}"

main() {
    check_root
    check_dependencies
    create_user_group
    install_application
    install_systemd_units
    setup_directories
    validate_configuration
    print_next_steps
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
       echo "This script must be run as root"
       exit 1
    fi
}

check_dependencies() {
    echo "Checking dependencies..."
    command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
    command -v systemctl >/dev/null || { echo "systemd not found"; exit 1; }
    command -v redis-server >/dev/null || echo "WARNING: redis-server not found (required at runtime)"
}

create_user_group() {
    echo "Creating njord user and group..."
    if ! getent group "$GROUP" >/dev/null; then
        groupadd --system "$GROUP"
    fi
    if ! getent passwd "$USER" >/dev/null; then
        useradd --system --gid "$GROUP" --home-dir "$INSTALL_DIR" \
                --shell /usr/sbin/nologin --comment "Njord Quant Service User" "$USER"
    fi
}

install_application() {
    echo "Installing application to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='.git' --exclude='venv' --exclude='__pycache__' \
          ./ "$INSTALL_DIR/"

    # Create virtualenv and install dependencies
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

    chown -R "$USER:$GROUP" "$INSTALL_DIR"
}

install_systemd_units() {
    echo "Installing systemd units to $SYSTEMD_DIR..."
    cp deploy/systemd/*.service "$SYSTEMD_DIR/"
    cp deploy/systemd/*.target "$SYSTEMD_DIR/"
    systemctl daemon-reload
}

setup_directories() {
    echo "Setting up directories..."
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$INSTALL_DIR/var/log/njord"
    mkdir -p "$INSTALL_DIR/var/state"

    chown -R "$USER:$GROUP" "$LOG_DIR"
    chown -R "$USER:$GROUP" "$INSTALL_DIR/var"
}

validate_configuration() {
    echo "Validating configuration..."
    if [[ ! -f "$INSTALL_DIR/config/base.yaml" ]]; then
        echo "WARNING: config/base.yaml not found"
    fi
    if [[ ! -f "$CONFIG_DIR/env.conf" ]]; then
        echo "WARNING: /etc/njord/env.conf not found (create from env.conf.example)"
    fi
}

print_next_steps() {
    cat <<EOF

Installation complete!

Next steps:
1. Configure environment: cp deploy/env.conf.example /etc/njord/env.conf
2. Edit configuration: vim /etc/njord/env.conf
3. Enable services: systemctl enable njord.target
4. Start services: systemctl start njord.target
5. Check status: systemctl status njord.target
6. View logs: journalctl -u njord-* -f

EOF
}

main "$@"
```

**Files:**
- `deploy/install.sh` (Installation script, ~250 lines)
- `deploy/uninstall.sh` (Removal script, ~100 lines)
- `deploy/env.conf.example` (Environment template, ~80 lines)
- `deploy/INSTALL.md` (Installation guide, ~200 lines)
- `tests/test_install.sh` (Installation smoke test)

**Acceptance:**
- Installation script creates user/group correctly
- Application files copied to install directory
- Virtualenv created and dependencies installed
- Systemd units installed and daemon reloaded
- Directories created with correct ownership
- **Test verifies installation in Docker container (isolated test)**
- **Test verifies uninstall script removes all artifacts**
- **Test verifies configuration validation catches missing files**
- INSTALL.md includes step-by-step instructions with verification commands
- `make fmt lint type test` green (shell scripts validated with shellcheck)

---

### Phase 15.2 — Configuration Packaging 📋
**Status:** Planned
**Dependencies:** 15.1 (Service Installation Script)
**Task:** Implement configuration management with encryption support (SOPS)

**Behavior:**
- Package configuration files for different environments (dev, staging, prod)
- Encrypt secrets using SOPS with age encryption
- Validate configuration against schema
- Support configuration versioning and rollback
- Document configuration parameters and sensible defaults

**Deliverables:**

#### 1. Environment Configurations
```yaml
# config/environments/production.yaml
app:
  env: production
  log_level: INFO
  log_dir: /var/log/njord

redis:
  host: 127.0.0.1
  port: 6379
  db: 0

risk:
  max_position_pct: 0.05
  max_daily_loss: 1000.0
  max_order_rate: 10

# Reference to encrypted secrets
secrets_file: /etc/njord/secrets.enc.yaml
```

#### 2. Encrypted Secrets (SOPS)
```yaml
# config/secrets.enc.yaml (encrypted with age/SOPS)
# Plaintext example (DO NOT COMMIT UNENCRYPTED):
binance:
    api_key: sk_live_xxxxx
    api_secret: xxxxx

smtp:
    username: alerts@njord.example.com
    password: xxxxx

webhooks:
    slack_url: https://hooks.slack.com/services/xxxxx
```

#### 3. Configuration Validator
```python
class ConfigValidator:
    """Validate configuration against schema and constraints."""

    def __init__(self, schema_path: Path):
        self.schema = self._load_schema(schema_path)

    def validate(self, config_path: Path) -> list[str]:
        """Validate configuration file.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        config = self._load_config(config_path)

        # Schema validation
        schema_errors = self._validate_schema(config)
        errors.extend(schema_errors)

        # Business rule validation
        if config.get("app", {}).get("env") == "live":
            if "secrets_file" not in config:
                errors.append("secrets_file required for live environment")

        # Risk limit validation
        risk = config.get("risk", {})
        if risk.get("max_position_pct", 0) > 0.2:
            errors.append("max_position_pct must be <= 0.2 (20%)")

        return errors
```

**Files:**
- `config/environments/development.yaml` (~100 lines)
- `config/environments/staging.yaml` (~100 lines)
- `config/environments/production.yaml` (~100 lines)
- `config/schemas/base_schema.yaml` (JSON schema, ~150 lines)
- `deploy/config_validator.py` (ConfigValidator, ~180 LOC)
- `deploy/encrypt_secrets.sh` (SOPS encryption helper, ~60 lines)
- `deploy/CONFIG.md` (Configuration guide, ~250 lines)

**Acceptance:**
- Environment configs cover dev/staging/prod
- Secrets template provided (secrets.enc.yaml.example)
- ConfigValidator enforces schema correctly
- Business rule validation catches invalid risk limits
- **Test verifies schema validation rejects invalid config**
- **Test verifies encryption/decryption workflow (SOPS integration)**
- **Test verifies production config requires secrets_file**
- CONFIG.md documents all configuration parameters with defaults
- `make fmt lint type test` green

---

### Phase 15.3 — Ansible Deployment Playbook (Optional) 📋
**Status:** Planned
**Dependencies:** 15.2 (Configuration Packaging)
**Task:** Create Ansible playbook for automated deployment to remote hosts

**Behavior:**
- Automate installation on remote hosts
- Support multi-host deployment (separate Redis, services, etc.)
- Idempotent operations (can run repeatedly)
- Configuration templating (Jinja2 for environment-specific values)
- Service health checks after deployment

**Deliverables:**

#### 1. Ansible Inventory
```ini
# deploy/ansible/inventory/production.ini
[redis]
redis01.njord.internal

[services]
trading01.njord.internal
trading02.njord.internal

[monitoring]
metrics01.njord.internal

[all:vars]
ansible_user=deploy
ansible_python_interpreter=/usr/bin/python3
njord_version=v1.0.0
njord_environment=production
```

#### 2. Main Playbook
```yaml
# deploy/ansible/deploy.yml
---
- name: Deploy Njord Quant Trading System
  hosts: services
  become: yes
  vars:
    njord_install_dir: /opt/njord_quant
    njord_user: njord
    njord_group: njord

  tasks:
    - name: Install system dependencies
      apt:
        name:
          - python3
          - python3-pip
          - python3-venv
          - redis-tools
        state: present
        update_cache: yes

    - name: Create njord user
      user:
        name: "{{ njord_user }}"
        group: "{{ njord_group }}"
        system: yes
        shell: /usr/sbin/nologin
        home: "{{ njord_install_dir }}"

    - name: Deploy application files
      synchronize:
        src: ../../
        dest: "{{ njord_install_dir }}"
        delete: yes
        rsync_opts:
          - "--exclude=.git"
          - "--exclude=venv"
          - "--exclude=__pycache__"

    - name: Create virtualenv and install dependencies
      pip:
        requirements: "{{ njord_install_dir }}/requirements.txt"
        virtualenv: "{{ njord_install_dir }}/venv"
        virtualenv_command: python3 -m venv

    - name: Template environment configuration
      template:
        src: templates/env.conf.j2
        dest: /etc/njord/env.conf
        owner: root
        group: "{{ njord_group }}"
        mode: '0640'

    - name: Install systemd units
      copy:
        src: "{{ item }}"
        dest: /etc/systemd/system/
        owner: root
        group: root
        mode: '0644'
      loop: "{{ lookup('fileglob', '../systemd/*.service', wantlist=True) }}"
      notify: reload systemd

    - name: Enable njord services
      systemd:
        name: njord.target
        enabled: yes
        daemon_reload: yes

    - name: Start njord services
      systemd:
        name: njord.target
        state: started

    - name: Wait for services to be healthy
      wait_for:
        host: 127.0.0.1
        port: 9090  # Metrics exporter
        timeout: 60

  handlers:
    - name: reload systemd
      systemd:
        daemon_reload: yes
```

**Files:**
- `deploy/ansible/deploy.yml` (Main playbook, ~200 lines)
- `deploy/ansible/inventory/production.ini` (~30 lines)
- `deploy/ansible/templates/env.conf.j2` (Jinja2 template, ~80 lines)
- `deploy/ansible/README.md` (Ansible usage guide, ~150 lines)

**Acceptance:**
- Playbook deploys to remote hosts successfully
- Idempotent: running twice doesn't break deployment
- Health checks verify services started
- Configuration templating works (environment-specific values)
- **Test verifies deployment in Vagrant/Docker environment**
- **Test verifies idempotency: second run shows no changes**
- **Test verifies rollback: revert to previous version**
- README.md includes quickstart and troubleshooting
- `make fmt lint type test` green (YAML syntax validated)

---

### Phase 15.4 — Operational Runbook 📋
**Status:** Planned
**Dependencies:** 15.3 (Ansible Deployment)
**Task:** Document operational procedures for common scenarios

**Deliverables:**

#### 1. Runbook Overview
**File:** `docs/ops/RUNBOOK.md`

Sections:
1. **Service Management:**
   - Start/stop/restart procedures
   - Check service status
   - View logs
   - Emergency shutdown (kill-switch)

2. **Configuration Management:**
   - Update configuration
   - Rotate secrets
   - Validate config changes
   - Rollback procedure

3. **Monitoring & Alerting:**
   - Check metrics dashboard
   - Investigate alerts
   - Silence false positives
   - Escalation procedures

4. **Incident Response:**
   - Kill-switch activation
   - Position liquidation
   - Service recovery
   - Post-incident review

5. **Maintenance:**
   - Dependency updates
   - Log rotation
   - Backup procedures
   - Performance tuning

#### 2. Quick Reference Cards
```bash
# Quick Reference: Service Management
# File: docs/ops/quick-ref-services.md

# Start all services
sudo systemctl start njord.target

# Stop all services
sudo systemctl stop njord.target

# Check status
sudo systemctl status njord.target

# View logs (all services)
sudo journalctl -u njord-* -f

# View logs (specific service)
sudo journalctl -u njord-risk-engine -f --since "1 hour ago"

# Restart single service
sudo systemctl restart njord-risk-engine

# Emergency kill-switch
sudo touch /tmp/njord_killswitch
# or
redis-cli SET njord:killswitch 1
```

#### 3. Troubleshooting Guide
**File:** `docs/ops/TROUBLESHOOTING.md`

Common Issues:
- Service fails to start → Check logs, validate config, verify Redis connection
- High memory usage → Check strategy count, review position sizes
- Kill-switch not triggering → Verify file permissions, check Redis connectivity
- Metrics not updating → Check exporter service, verify Prometheus scrape config
- Orders not executing → Check broker dry-run mode, verify API credentials

**Files:**
- `docs/ops/RUNBOOK.md` (~500 lines)
- `docs/ops/quick-ref-services.md` (~100 lines)
- `docs/ops/quick-ref-alerts.md` (~100 lines)
- `docs/ops/TROUBLESHOOTING.md` (~400 lines)
- `docs/ops/INCIDENT_TEMPLATE.md` (Post-incident review template, ~150 lines)

**Acceptance:**
- RUNBOOK.md covers all 5 operational areas
- Quick reference cards include most common commands
- TROUBLESHOOTING.md addresses known failure modes
- All bash commands in docs are valid (tested)
- Incident template includes root cause analysis section
- **Documentation validated by manual testing of all procedures**
- `make fmt lint type test` green (no code changes)

---

### Phase 15.5 — Health Check Endpoints 📋
**Status:** Planned
**Dependencies:** 15.4 (Operational Runbook)
**Task:** Implement HTTP health check endpoints for all services

**Behavior:**
- Expose /health endpoint on each service
- Return 200 OK when healthy, 503 Service Unavailable when degraded
- Include dependency checks (Redis connectivity, data freshness)
- Support readiness vs liveness checks (Kubernetes-style)
- Integrate with service monitoring and auto-restart

**API:**
```python
from aiohttp import web

class HealthCheckServer:
    """HTTP server exposing health check endpoints.

    Endpoints:
    - GET /health: Overall health status
    - GET /health/liveness: Liveness probe (process alive)
    - GET /health/readiness: Readiness probe (ready to serve traffic)
    """

    def __init__(
        self,
        service_name: str,
        bind_host: str = "127.0.0.1",
        bind_port: int = 8080,
        dependencies: list[HealthCheck] | None = None
    ):
        self.service_name = service_name
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.dependencies = dependencies or []
        self.app = web.Application()
        self._setup_routes()

    async def health(self, request: web.Request) -> web.Response:
        """Overall health check (liveness + readiness)."""
        liveness = await self._check_liveness()
        readiness = await self._check_readiness()

        if not liveness["healthy"]:
            return web.json_response(liveness, status=503)
        if not readiness["healthy"]:
            return web.json_response(readiness, status=503)

        return web.json_response({
            "service": self.service_name,
            "status": "healthy",
            "timestamp": time_ns(),
            "liveness": liveness,
            "readiness": readiness
        })

    async def _check_liveness(self) -> dict[str, Any]:
        """Liveness check: is process alive and not deadlocked?"""
        return {
            "healthy": True,
            "checks": {
                "process": "alive",
                "memory": self._check_memory()
            }
        }

    async def _check_readiness(self) -> dict[str, Any]:
        """Readiness check: are dependencies healthy?"""
        checks = {}
        healthy = True

        for dep in self.dependencies:
            result = await dep.check()
            checks[dep.name] = result
            if not result["healthy"]:
                healthy = False

        return {
            "healthy": healthy,
            "checks": checks
        }

class RedisHealthCheck(HealthCheck):
    """Health check for Redis dependency."""

    async def check(self) -> dict[str, Any]:
        try:
            await self.redis.ping()
            return {"healthy": True, "latency_ms": latency}
        except Exception as e:
            return {"healthy": False, "error": str(e)}
```

**Requirements:**
- All services expose health endpoints
- Liveness checks detect deadlocks and unresponsive processes
- Readiness checks verify dependencies (Redis, data freshness)
- Support configurable bind host/port (default: localhost-only)
- Lightweight overhead (<1ms response time)

**Constraints:**
- No new runtime dependencies (use aiohttp from existing stack)
- Bind to localhost by default (security)
- Must not block event loop (async checks)

**Files:**
- `core/health.py` (HealthCheckServer, HealthCheck base, ~180 LOC)
- `core/health_checks.py` (RedisHealthCheck, DataFreshnessCheck, ~100 LOC)
- Integration in all service __main__.py files (~10 LOC each)
- `tests/test_health_checks.py`

**Acceptance:**
- HealthCheckServer exposes /health, /health/liveness, /health/readiness
- Returns 200 when healthy, 503 when unhealthy
- Liveness check detects process alive
- Readiness check verifies Redis connectivity
- **Test verifies health endpoint response format**
- **Test verifies degraded state returns 503**
- **Test verifies dependency failure detected (mock Redis down)**
- **Performance test: health check responds in <1ms**
- All services integrate health checks (verify in service startup logs)
- `make fmt lint type test` green

---

### Phase 15.6 — Backup & Recovery Procedures 📋
**Status:** Planned
**Dependencies:** 15.5 (Health Check Endpoints)
**Task:** Document and implement backup/recovery procedures for state and logs

**Deliverables:**

#### 1. Backup Script
```bash
#!/usr/bin/env bash
# deploy/backup.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/njord}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

backup_logs() {
    echo "Backing up logs..."
    tar -czf "$BACKUP_DIR/logs_$TIMESTAMP.tar.gz" \
        /var/log/njord/*.ndjson \
        /opt/njord_quant/var/log/njord/*.ndjson
}

backup_state() {
    echo "Backing up state..."
    tar -czf "$BACKUP_DIR/state_$TIMESTAMP.tar.gz" \
        /opt/njord_quant/var/state/
}

backup_config() {
    echo "Backing up configuration..."
    tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" \
        /etc/njord/ \
        /opt/njord_quant/config/
}

cleanup_old_backups() {
    echo "Cleaning up backups older than $RETENTION_DAYS days..."
    find "$BACKUP_DIR" -type f -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
}

main() {
    mkdir -p "$BACKUP_DIR"
    backup_logs
    backup_state
    backup_config
    cleanup_old_backups
    echo "Backup complete: $BACKUP_DIR"
}

main "$@"
```

#### 2. Recovery Procedure
**File:** `docs/ops/RECOVERY.md`

Sections:
1. **State Recovery:**
   - Restore position snapshots
   - Restore order history
   - Verify data integrity

2. **Log Recovery:**
   - Restore journal files
   - Replay events if needed
   - Rebuild derived state

3. **Configuration Recovery:**
   - Restore config files
   - Decrypt secrets
   - Validate configuration

4. **Disaster Recovery:**
   - Full system rebuild from backups
   - Point-in-time recovery
   - Data consistency validation

**Files:**
- `deploy/backup.sh` (Backup script, ~150 lines)
- `deploy/restore.sh` (Restore script, ~200 lines)
- `deploy/verify_backup.sh` (Backup integrity check, ~100 lines)
- `docs/ops/RECOVERY.md` (Recovery guide, ~300 lines)
- `tests/test_backup_restore.sh` (Backup/restore test)

**Acceptance:**
- Backup script captures logs, state, and config
- Retention policy deletes old backups correctly
- Restore script recovers files to correct locations
- **Test verifies backup/restore round-trip: backup → restore → verify**
- **Test verifies retention policy: old backups deleted after N days**
- RECOVERY.md includes step-by-step restore procedures
- Disaster recovery procedure tested (manual verification)
- `make fmt lint type test` green (shell scripts validated)

---

### Phase 15.7 — Deployment Documentation 📋
**Status:** Planned
**Dependencies:** 15.6 (Backup & Recovery)
**Task:** Comprehensive deployment guide covering all deployment scenarios

**Deliverables:**

#### 1. Deployment Guide
**File:** `docs/deployment/DEPLOYMENT.md`

Sections:
1. **Prerequisites:**
   - System requirements (OS, Python, Redis, etc.)
   - Network requirements (ports, firewalls)
   - Access requirements (SSH keys, credentials)

2. **Installation Methods:**
   - Manual installation (install.sh)
   - Ansible deployment (multi-host)
   - Docker deployment (containerized)

3. **Configuration:**
   - Environment-specific configs
   - Secret management (SOPS)
   - Configuration validation

4. **Verification:**
   - Service health checks
   - Smoke tests
   - Integration tests

5. **Post-Deployment:**
   - Monitoring setup
   - Alert configuration
   - Backup scheduling

#### 2. Deployment Checklist
**File:** `docs/deployment/CHECKLIST.md`

```markdown
# Deployment Checklist

## Pre-Deployment
- [ ] Review deployment plan
- [ ] Backup current state
- [ ] Notify stakeholders
- [ ] Schedule maintenance window

## Deployment
- [ ] Stop services gracefully
- [ ] Deploy new version
- [ ] Migrate configuration
- [ ] Update systemd units
- [ ] Start services

## Verification
- [ ] Health checks pass
- [ ] Metrics reporting
- [ ] Alerts configured
- [ ] Logs streaming

## Post-Deployment
- [ ] Monitor for 1 hour
- [ ] Verify trading activity
- [ ] Document issues
- [ ] Notify completion
```

**Files:**
- `docs/deployment/DEPLOYMENT.md` (~600 lines)
- `docs/deployment/CHECKLIST.md` (~150 lines)
- `docs/deployment/DOCKER.md` (Docker deployment, ~200 lines)
- `docs/deployment/SECURITY.md` (Security hardening, ~250 lines)

**Acceptance:**
- DEPLOYMENT.md covers all installation methods
- CHECKLIST.md provides step-by-step verification
- DOCKER.md includes Dockerfile and docker-compose.yml examples
- SECURITY.md covers hardening best practices
- All documentation validated by deployment test
- `make fmt lint type test` green (no code changes)

---

**Phase 15 Acceptance Criteria:**
- [ ] All 7 tasks completed (15.0-15.7)
- [ ] `make fmt lint type test` green
- [ ] Systemd units for all services with correct dependencies
- [ ] Installation script deploys successfully to clean host
- [ ] Configuration packaging supports dev/staging/prod environments
- [ ] Ansible playbook (optional) deploys to remote hosts
- [ ] Operational runbook covers all common procedures
- [ ] Health check endpoints implemented for all services
- [ ] Backup/recovery procedures documented and tested
- [ ] Deployment documentation comprehensive and validated
- [ ] Security hardening applied:
  - User isolation (njord user)
  - Capability restrictions (NoNewPrivileges)
  - Read-only paths enforced
  - Resource limits enforced
- [ ] All scripts validated with shellcheck
- [ ] Manual deployment test completed successfully

---

## Integration with Existing System

### Deployment Flow
```
Source Code
    ↓
Git Tag (version)
    ↓
CI/CD Pipeline (optional)
    ↓
Deployment Method:
    - install.sh (manual)
    - Ansible playbook (automated)
    - Docker (containerized)
    ↓
systemd Service Units
    ↓
Health Check Verification
    ↓
Production Services Running
```

### Example Deployment Session
```bash
# 1. Install to production host
sudo deploy/install.sh

# 2. Configure environment
sudo cp deploy/env.conf.example /etc/njord/env.conf
sudo vim /etc/njord/env.conf  # Edit settings

# 3. Encrypt secrets
deploy/encrypt_secrets.sh config/secrets.yaml

# 4. Validate configuration
python deploy/config_validator.py config/environments/production.yaml

# 5. Enable and start services
sudo systemctl enable njord.target
sudo systemctl start njord.target

# 6. Verify health
curl http://localhost:9090/health

# 7. Monitor logs
sudo journalctl -u njord-* -f
```

---

## Dependencies Summary

```
Phase 14 (Simulation Harness) ✅
    └─> Phase 15.0 (Systemd Service Templates) — Unit files with dependencies
            └─> 15.1 (Service Installation) — Deploy script
                    └─> 15.2 (Configuration Packaging) — Env configs + SOPS
                            └─> 15.3 (Ansible Playbook) — Automated deployment
                                    └─> 15.4 (Operational Runbook) — Ops procedures
                                            └─> 15.5 (Health Checks) — Service monitoring
                                                    └─> 15.6 (Backup & Recovery) — State preservation
                                                            └─> 15.7 (Deployment Docs) — Comprehensive guide
```

Each task builds on the previous, progressing from basic service units to full deployment automation and operational procedures.

---
