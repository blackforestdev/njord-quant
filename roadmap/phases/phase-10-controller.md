## Phase 10 — Live Trade Controller 📋

**Purpose:** Implement unified CLI for managing all trading services with config hot-reload and session journaling.

**Current Status:** Phase 9 complete — Metrics & Telemetry fully operational
**Next Phase:** Phase 11 — Monitoring & Alerts

---

### Phase 10.0 — Controller Contracts 📋
**Status:** Planned
**Dependencies:** 9.9 (Telemetry Documentation)
**Task:** Define service control contracts and session tracking

**Contracts:**
```python
@dataclass(frozen=True)
class ServiceStatus:
    """Status of a single service."""
    service_name: str
    status: Literal["running", "stopped", "starting", "stopping", "error"]
    pid: int | None
    uptime_seconds: int
    last_error: str | None
    timestamp_ns: int

@dataclass(frozen=True)
class SessionSnapshot:
    """Trading session metadata."""
    session_id: str
    start_ts_ns: int
    end_ts_ns: int | None
    services: list[str]  # Service names in session
    config_hash: str  # SHA256 of config files
    status: Literal["active", "stopped", "error"]

@dataclass(frozen=True)
class ControlCommand:
    """Command to control services."""
    command: Literal["start", "stop", "restart", "reload", "status"]
    service_names: list[str]  # Empty list = all services
    session_id: str
    timestamp_ns: int
```

**Files:**
- `controller/contracts.py` (80 LOC)
- `tests/test_controller_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- ServiceStatus includes PID tracking
- SessionSnapshot tracks config hash for reload detection
- `make fmt lint type test` green

---

### Phase 10.1 — Service Registry 📋
**Status:** Planned
**Dependencies:** 10.0 (Controller Contracts)
**Task:** Implement service discovery and registration

**Behavior:**
- Auto-discover services in `apps/` directory
- Register service metadata (name, entry point, dependencies)
- Support service dependency ordering (start risk_engine before broker)
- Validate service existence before operations
- Support service groups (e.g., "live", "paper", "backtest")

**API:**
```python
class ServiceRegistry:
    def __init__(self, apps_dir: Path = Path("apps")): ...

    def discover_services(self) -> dict[str, ServiceMetadata]:
        """Discover all services in apps/ directory.

        Returns:
            Dict mapping service name to metadata
        """
        pass

    def get_service(self, name: str) -> ServiceMetadata:
        """Get service metadata by name.

        Raises:
            KeyError: If service not found
        """
        pass

    def get_start_order(
        self,
        service_names: list[str]
    ) -> list[str]:
        """Get topologically sorted start order based on dependencies.

        Returns:
            List of service names in start order
        """
        pass

    def get_service_group(
        self,
        group: Literal["live", "paper", "backtest", "all"]
    ) -> list[str]:
        """Get service names in group.

        Returns:
            List of service names
        """
        pass
```

**Service Groups:**
```yaml
groups:
  live:
    - md_ingest
    - risk_engine
    - broker_binanceus
    - portfolio_manager
    - metric_aggregator

  paper:
    - md_ingest
    - risk_engine
    - paper_trader
    - portfolio_manager
    - metric_aggregator

  backtest:
    - []  # No persistent services for backtest
```

**Files:**
- `controller/registry.py` (150 LOC)
- `controller/metadata.py` (ServiceMetadata dataclass, 50 LOC)
- `tests/test_service_registry.py`

**Acceptance:**
- Discovers all services in apps/ directory
- Correctly orders services by dependencies
- Validates service existence
- Service groups defined and retrievable
- Handles missing services gracefully (KeyError)
- `make fmt lint type test` green

---

### Phase 10.2 — Process Manager 📋
**Status:** Planned
**Dependencies:** 10.1 (Service Registry)
**Task:** Manage service process lifecycle (start/stop/restart)

**Behavior:**
- Start services as background processes
- **Safety: Check kill-switch before starting live services** (respect Phase 2 protections)
- **Safety: Require NJORD_ENABLE_LIVE=1 env var for live broker/trading services**
- Track PIDs and monitor process health
- Stop services gracefully (SIGTERM, then SIGKILL after timeout)
- Restart crashed services (optional auto-restart)
- Capture stdout/stderr to log files
- Environment variable injection

**API:**
```python
class ProcessManager:
    def __init__(
        self,
        registry: ServiceRegistry,
        log_dir: Path = Path("var/log/njord")
    ): ...

    async def start_service(
        self,
        service_name: str,
        config_root: Path = Path(".")
    ) -> ServiceStatus:
        """Start a service process.

        Returns:
            ServiceStatus with PID and status
        """
        pass

    async def stop_service(
        self,
        service_name: str,
        timeout_seconds: int = 10
    ) -> ServiceStatus:
        """Stop a service gracefully.

        Args:
            timeout_seconds: Wait for SIGTERM, then SIGKILL

        Returns:
            ServiceStatus after stopping
        """
        pass

    async def restart_service(
        self,
        service_name: str
    ) -> ServiceStatus:
        """Restart a service (stop + start).

        Returns:
            ServiceStatus after restart
        """
        pass

    def get_status(
        self,
        service_name: str
    ) -> ServiceStatus:
        """Get current service status.

        Returns:
            ServiceStatus with PID, uptime, status
        """
        pass

    async def monitor_health(
        self,
        service_name: str,
        interval_seconds: int = 5
    ) -> AsyncIterator[ServiceStatus]:
        """Monitor service health continuously.

        Yields:
            ServiceStatus updates
        """
        pass
```

**Files:**
- `controller/process.py` (250 LOC)
- `tests/test_process_manager.py`

**Acceptance:**
- Starts services as background processes
- **Safety: Checks kill-switch state before starting live services** (Phase 2 integration)
- **Safety: Validates NJORD_ENABLE_LIVE=1 env var for live broker** (prevents accidental live trading)
- Tracks PIDs correctly
- Stops services gracefully (SIGTERM before SIGKILL)
- Captures stdout/stderr to log files
- Monitors process health (detects crashes)
- Timeout enforcement on stop operations
- Test includes process lifecycle (start/stop/restart)
- Test includes kill-switch enforcement (refuses to start if tripped)
- `make fmt lint type test` green

---

### Phase 10.3 — Config Hot-Reload 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager)
**Task:** Implement configuration hot-reload without service restart

**Behavior:**
- Watch config files for changes
  - **Use inotify if available (Linux), otherwise fall back to polling every 5 seconds**
  - **Cross-platform: Detect platform and use appropriate method**
- Compute config hash (SHA256) for change detection
- Send reload signal to services (SIGHUP or Redis message)
- Services reload config on signal (no restart)
- Validate config before reload (reject invalid changes)
- Journal config changes with timestamps

**API:**
```python
class ConfigReloader:
    def __init__(
        self,
        bus: BusProto,
        config_root: Path = Path(".")
    ): ...

    async def watch_config(self) -> None:
        """Watch config files for changes."""
        pass

    def compute_config_hash(
        self,
        config_files: list[Path]
    ) -> str:
        """Compute SHA256 hash of config files.

        Returns:
            Hex-encoded SHA256 hash
        """
        pass

    async def reload_service_config(
        self,
        service_name: str
    ) -> bool:
        """Trigger config reload for service.

        Returns:
            True if reload successful
        """
        pass

    def validate_config(
        self,
        config_path: Path
    ) -> tuple[bool, str | None]:
        """Validate config file before reload.

        Returns:
            (valid, error_message)
        """
        pass
```

**Reload Mechanism:**
```python
# Option 1: SIGHUP signal
os.kill(pid, signal.SIGHUP)

# Option 2: Redis pub/sub (preferred for cross-host)
await bus.publish_json("controller.reload", {"service": service_name})

# Services listen for reload:
async for msg in bus.subscribe("controller.reload"):
    if msg["service"] == self.service_name:
        self.config = load_config()
        logger.info("config_reloaded")
```

**Files:**
- `controller/reload.py` (180 LOC)
- Update `apps/*/main.py` to handle reload signal (+20 LOC each)
- `tests/test_config_reload.py`

**Acceptance:**
- Detects config file changes (inotify on Linux, polling fallback for cross-platform)
- **Fallback mechanism tested: works on systems without inotify**
- Computes config hash correctly (SHA256)
- Sends reload signal to services (Redis pub/sub preferred)
- Services reload config without restart
- Config validation prevents invalid reloads
- Config changes journaled with timestamps
- Test includes reload simulation
- Test includes polling fallback path
- `make fmt lint type test` green

---

### Phase 10.4 — Session Manager 📋
**Status:** Planned
**Dependencies:** 10.3 (Config Hot-Reload)
**Task:** Track trading sessions and journal lifecycle events

**Behavior:**
- Create session on controller start
- Assign unique session_id (UUID)
- Journal session events (start, stop, config_reload, error)
- Track session metadata (config hash, services, uptime)
- Persist sessions to journal for audit
- Support session queries (current, historical)

**API:**
```python
class SessionManager:
    def __init__(
        self,
        journal_dir: Path = Path("var/log/njord")
    ): ...

    def create_session(
        self,
        services: list[str],
        config_hash: str
    ) -> SessionSnapshot:
        """Create new trading session.

        Returns:
            SessionSnapshot with session_id
        """
        pass

    def end_session(
        self,
        session_id: str
    ) -> SessionSnapshot:
        """End trading session.

        Returns:
            SessionSnapshot with end_ts_ns
        """
        pass

    def get_current_session(self) -> SessionSnapshot | None:
        """Get current active session.

        Returns:
            SessionSnapshot or None if no active session
        """
        pass

    def get_session_history(
        self,
        limit: int = 10
    ) -> list[SessionSnapshot]:
        """Get recent session history.

        Returns:
            List of SessionSnapshots (newest first)
        """
        pass

    def journal_event(
        self,
        session_id: str,
        event_type: str,
        details: dict[str, Any]
    ) -> None:
        """Journal session lifecycle event."""
        pass
```

**Session Journal Format (NDJSON):**
```json
{"session_id":"a1b2c3","event":"session_start","ts_ns":1234567890,"services":["risk_engine","paper_trader"],"config_hash":"abc123"}
{"session_id":"a1b2c3","event":"config_reload","ts_ns":1234567900,"config_hash":"def456"}
{"session_id":"a1b2c3","event":"service_crashed","ts_ns":1234567910,"service":"paper_trader","error":"connection lost"}
{"session_id":"a1b2c3","event":"session_end","ts_ns":1234567920}
```

**Files:**
- `controller/session.py` (150 LOC)
- `tests/test_session_manager.py`

**Acceptance:**
- Creates unique session IDs (UUID)
- Journals session lifecycle events (NDJSON)
- Tracks config hash for each session
- Retrieves current and historical sessions
- Session end timestamp recorded correctly
- Test includes session lifecycle (create/end/query)
- `make fmt lint type test` green

---

### Phase 10.5 — Log Aggregation 📋
**Status:** Planned
**Dependencies:** 10.4 (Session Manager)
**Task:** Aggregate and tail logs from multiple services

**Behavior:**
- Read logs from all service log files
- Support log tailing (--follow)
- Filter logs by service, level, time range
- Merge logs by timestamp (chronological order)
- Colorize by service/level
- Support log search (grep-like)

**API:**
```python
class LogAggregator:
    def __init__(
        self,
        log_dir: Path = Path("var/log/njord")
    ): ...

    def read_logs(
        self,
        service_names: list[str] | None = None,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None,
        level: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Read logs with filters.

        Returns:
            List of log entries (NDJSON parsed)
        """
        pass

    async def tail_logs(
        self,
        service_names: list[str] | None = None,
        level: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Tail logs continuously.

        Yields:
            Log entries as they arrive
        """
        pass

    def search_logs(
        self,
        pattern: str,
        service_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Search logs by pattern.

        Returns:
            Matching log entries
        """
        pass

    def merge_by_timestamp(
        self,
        log_entries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge and sort logs by timestamp.

        Returns:
            Chronologically ordered log entries
        """
        pass
```

**Files:**
- `controller/logs.py` (200 LOC)
- `tests/test_log_aggregator.py`

**Acceptance:**
- Reads logs from service log files (NDJSON)
- Merges logs by timestamp (chronological)
- Tail mode works (--follow)
- Filters by service, level, time range
- Search functionality works (regex)
- Colorized output by service/level (TTY detection)
- Test includes log aggregation scenarios
- `make fmt lint type test` green

---

### Phase 10.6 — CLI Framework 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager), 10.3 (Config Hot-Reload), 10.4 (Session Manager), 10.5 (Log Aggregation)
**Task:** Implement `njord-ctl` unified CLI tool

**Behavior:**
- Single entrypoint: `njord-ctl <command> [options]`
- Commands: start, stop, restart, reload, status, logs, session
- Support service selection (--service, --group, --all)
- Colorized output (optional, detect TTY)
- JSON output mode (--json)
- Dry-run mode (--dry-run)

**CLI Commands:**
```bash
# Start services
njord-ctl start --group live
njord-ctl start --service risk_engine,paper_trader
njord-ctl start --all

# Stop services
njord-ctl stop --group live
njord-ctl stop --service risk_engine
njord-ctl stop --all

# Restart services
njord-ctl restart --service paper_trader

# Reload config (no restart)
njord-ctl reload --all

# Check status
njord-ctl status
njord-ctl status --service risk_engine --json

# View logs
njord-ctl logs --service risk_engine --follow --lines 100

# Session management
njord-ctl session current
njord-ctl session history --limit 10
```

**API:**
```python
class NjordCLI:
    def __init__(
        self,
        config_root: Path = Path(".")
    ): ...

    def build_parser(self) -> argparse.ArgumentParser:
        """Build argument parser with all commands."""
        pass

    async def cmd_start(self, args: argparse.Namespace) -> int:
        """Handle start command."""
        pass

    async def cmd_stop(self, args: argparse.Namespace) -> int:
        """Handle stop command."""
        pass

    async def cmd_status(self, args: argparse.Namespace) -> int:
        """Handle status command."""
        pass

    async def cmd_reload(self, args: argparse.Namespace) -> int:
        """Handle reload command."""
        pass

    async def cmd_logs(self, args: argparse.Namespace) -> int:
        """Handle logs command."""
        pass

    async def cmd_session(self, args: argparse.Namespace) -> int:
        """Handle session command."""
        pass

    def format_output(
        self,
        data: Any,
        json_mode: bool = False
    ) -> str:
        """Format output (JSON or human-readable)."""
        pass
```

**Files:**
- `scripts/njord_ctl.py` (300 LOC)
- `controller/cli.py` (CLI helper utilities, 100 LOC)
- `tests/test_njord_ctl.py`

**Acceptance:**
- All commands implemented (start/stop/restart/reload/status/logs/session)
- Service selection works (--service, --group, --all)
- JSON output mode functional (--json)
- Colorized output when TTY detected
- Dry-run mode shows actions without executing (--dry-run)
- Error handling with clear messages
- Logs command integrates with LogAggregator (10.5)
- Test includes all CLI commands
- `make fmt lint type test` green

---

### Phase 10.7 — Service Health Checks 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager), 10.6 (CLI Framework)
**Task:** Implement health check probes for services

**Behavior:**
- Define health check endpoints per service
- Support HTTP health checks (GET /health)
- Support Redis ping checks
- Aggregate health status across services
- Auto-restart unhealthy services (optional)
- Expose overall system health

**API:**
```python
class HealthChecker:
    def __init__(
        self,
        process_manager: ProcessManager,
        bus: BusProto
    ): ...

    async def check_service_health(
        self,
        service_name: str
    ) -> tuple[bool, str]:
        """Check service health.

        Returns:
            (healthy, status_message)
        """
        pass

    async def check_http_endpoint(
        self,
        url: str,
        timeout_seconds: int = 5
    ) -> bool:
        """Check HTTP health endpoint.

        Returns:
            True if endpoint returns 200
        """
        pass

    async def check_redis_connectivity(
        self,
        redis_url: str
    ) -> bool:
        """Check Redis connectivity.

        Returns:
            True if Redis ping succeeds
        """
        pass

    async def monitor_all_services(
        self,
        interval_seconds: int = 30
    ) -> AsyncIterator[dict[str, bool]]:
        """Monitor all services continuously.

        Yields:
            Dict mapping service name to health status
        """
        pass
```

**Health Check Definitions:**
```yaml
health_checks:
  risk_engine:
    type: redis
    interval: 30

  paper_trader:
    type: redis
    interval: 30

  metric_aggregator:
    type: http
    url: http://localhost:9090/health
    interval: 30

  metrics_dashboard:
    type: http
    url: http://localhost:8080/health
    interval: 60
```

**Files:**
- `controller/health.py` (180 LOC)
- `config/health_checks.yaml` (health check definitions)
- Update services with `/health` endpoints (+20 LOC each)
- `tests/test_health_checker.py`

**Acceptance:**
- HTTP health checks functional (GET /health → 200)
- Redis connectivity checks functional (ping)
- Aggregates health status across services
- Monitoring loop runs continuously
- Auto-restart on unhealthy service (configurable)
- Test includes health check scenarios (healthy/unhealthy)
- `make fmt lint type test` green

---

### Phase 10.8 — Controller Service 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager), 10.4 (Session Manager), 10.7 (Service Health Checks)
**Task:** Long-running controller daemon for session management

**Behavior:**
- Run as persistent daemon (background process)
- Manage session lifecycle automatically
- Monitor service health continuously
- Auto-restart crashed services (configurable)
- Expose control API (HTTP or Unix socket)
- Journal controller events

**API:**
```python
class ControllerDaemon:
    def __init__(
        self,
        config: Config,
        session_manager: SessionManager,
        process_manager: ProcessManager,
        health_checker: HealthChecker
    ): ...

    async def start(self) -> None:
        """Start controller daemon."""
        pass

    async def run(self) -> None:
        """Main daemon loop."""
        pass

    async def handle_service_crash(
        self,
        service_name: str
    ) -> None:
        """Handle service crash (auto-restart if enabled)."""
        pass

    async def expose_control_api(
        self,
        port: int = 9091,
        bind_host: str = "127.0.0.1"
    ) -> None:
        """Expose HTTP control API.

        Security:
            - Default bind to localhost only (127.0.0.1)
            - Require Bearer token auth for all endpoints
            - Token from env var NJORD_CONTROLLER_TOKEN
            - Reject requests without valid token (401 Unauthorized)

        Endpoints:
            GET /status (requires auth)
            POST /start (requires auth)
            POST /stop (requires auth)
            POST /reload (requires auth)
        """
        pass
```

**Daemon Features:**
- Runs in background (daemonize or systemd)
- Monitors all services (health checks)
- Auto-restart on crash (configurable per service)
- **Exposes HTTP API for remote control (localhost-only by default, token auth required)**
- **Security: Bearer token authentication (NJORD_CONTROLLER_TOKEN env var)**
- Graceful shutdown (SIGTERM handler)

**Files:**
- `apps/controller/main.py` (200 LOC)
- `controller/daemon.py` (150 LOC)
- `tests/test_controller_daemon.py`

**Acceptance:**
- Daemon runs in background
- Monitors service health continuously
- Auto-restarts crashed services (configurable)
- HTTP control API functional (start/stop/status/reload)
- **Security: API binds to localhost only by default** (127.0.0.1)
- **Security: Bearer token authentication enforced** (NJORD_CONTROLLER_TOKEN)
- **Security: Rejects requests without valid token (401 Unauthorized)**
- Graceful shutdown on SIGTERM
- Journals controller events (NDJSON)
- Test includes daemon lifecycle
- Test includes auth enforcement (valid/invalid token scenarios)
- `make fmt lint type test` green

---

### Phase 10.9 — Controller Documentation 📋
**Status:** Planned
**Dependencies:** 10.8 (Controller Service)
**Task:** Document controller system and operational procedures

**Deliverables:**

**1. CLI Reference**
- Complete command documentation (`njord-ctl --help` output)
- Command examples for common tasks
- Service group definitions
- Configuration options

**2. Session Management Guide**
- Session lifecycle explanation
- Session journaling format
- Session queries and history
- Config hot-reload procedures

**3. Operations Runbook**
- Starting/stopping services
- Monitoring service health
- Handling crashed services
- Log aggregation and search
- Troubleshooting common issues

**4. API Documentation**
- Controller HTTP API endpoints
- Health check probe definitions
- Service registry format
- Process manager usage

**Files:**
- `docs/controller/cli_reference.md`
- `docs/controller/session_management.md`
- `docs/controller/operations_runbook.md`
- `docs/controller/api_reference.md`
- `tests/test_controller_docs.py` (validate links, code examples)

**Acceptance:**
- CLI reference complete (all commands documented)
- Session management guide tested (follow procedures)
- Operations runbook covers common scenarios
- API docs include working code examples
- All markdown links valid
- Code examples in docs execute without errors
- `make fmt lint type test` green

---

**Phase 10 Acceptance Criteria:**
- [ ] All 10 tasks completed (10.0-10.9)
- [ ] `make fmt lint type test` green
- [ ] `njord-ctl` CLI functional with all commands
- [ ] Services start/stop/restart via controller
- [ ] Config hot-reload works without service restart
- [ ] Session journaling tracks all lifecycle events
- [ ] Health checks monitor all services
- [ ] Log aggregation merges and tails logs correctly
- [ ] Controller daemon runs as persistent service
- [ ] Documentation complete and verified
- [ ] No new runtime dependencies (stdlib + existing stack only)
- [ ] All timestamps use `*_ns` suffix
- [ ] Graceful shutdown on SIGTERM (all services)

---

## Integration with Existing System

### Controller Flow
```
njord-ctl start --group live
    ↓
ServiceRegistry → get_service_group("live")
    ↓
ProcessManager → start_service(each service)
    ↓
SessionManager → create_session(services, config_hash)
    ↓
HealthChecker → monitor_all_services()
    ↓
Services Running (risk_engine, broker, etc.)
    ↓
ConfigReloader → watch_config() → reload on change
    ↓
SessionManager → journal_event("config_reload")
    ↓
njord-ctl stop --all
    ↓
ProcessManager → stop_service(each service, SIGTERM)
    ↓
SessionManager → end_session(session_id)
```

### Example Controller Session
```bash
# 1. Start controller daemon
njord-ctl daemon start

# 2. Start live trading services
njord-ctl start --group live

# 3. Check status
njord-ctl status
# Output:
# SERVICE           STATUS    PID     UPTIME
# md_ingest         running   1234    00:15:32
# risk_engine       running   1235    00:15:31
# broker_binanceus  running   1236    00:15:30
# portfolio_manager running   1237    00:15:29
# metric_aggregator running   1238    00:15:28

# 4. Reload config (no restart)
njord-ctl reload --all

# 5. Tail logs
njord-ctl logs --service risk_engine --follow

# 6. Check session
njord-ctl session current
# Output:
# SESSION_ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
# STARTED:    2025-10-01 14:30:00 UTC
# UPTIME:     01:23:45
# SERVICES:   5 running
# CONFIG:     abc123def456 (no changes)

# 7. Stop all services
njord-ctl stop --all

# 8. Stop controller daemon
njord-ctl daemon stop
```

---

## Dependencies Summary

```
Phase 9 (Metrics & Telemetry) ✅
    └─> Phase 10.0 (Controller Contracts)
            └─> 10.1 (Service Registry)
                    └─> 10.2 (Process Manager) ━━━━┓
                            └─> 10.3 (Config Hot-Reload) ━━┓
                                    └─> 10.4 (Session Manager) ━┓
                                            └─> 10.5 (Log Aggregation) ━┓
                                                    │
                                                    └─> 10.6 (CLI Framework) ⭐
                                                            │  [Multi-deps: 10.2, 10.3, 10.4, 10.5]
                                                            │
                                                            └─> 10.7 (Service Health Checks)
                                                                    │  [Also depends: 10.2]
                                                                    │
                                                                    └─> 10.8 (Controller Service)
                                                                            │  [Also depends: 10.2, 10.4]
                                                                            │
                                                                            └─> 10.9 (Controller Docs)
```

**Dependency Notes:**
- **10.5 (Log Aggregation)** reordered before CLI to satisfy `logs` command dependency
- **10.6 (CLI Framework)** has explicit multi-dependencies on 10.2, 10.3, 10.4, 10.5
- **10.7 (Health Checks)** also depends on 10.2 (ProcessManager for monitoring)
- **10.8 (Controller Service)** also depends on 10.2 (ProcessManager), 10.4 (SessionManager)

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---
