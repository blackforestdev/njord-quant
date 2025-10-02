## Phase 12 — Compliance & Audit 📋

**Purpose:** Implement comprehensive audit trail, deterministic replay validation, and regulatory compliance tooling.

**Current Status:** Phase 11 complete — Monitoring & Alerts fully operational
**Next Phase:** Phase 13 — Advanced Strategy Toolkit

---

### Phase 12.0 — Audit Contracts 📋
**Status:** Planned
**Dependencies:** 11.10 (Alert Documentation)
**Task:** Define audit-specific contracts and event types

**Contracts:**
```python
@dataclass(frozen=True)
class AuditEvent:
    """Immutable audit log entry."""
    event_id: str  # UUID
    timestamp_ns: int
    event_type: Literal["order", "fill", "risk_decision", "config_change", "killswitch", "session"]
    actor: str  # User, service name, or "system"
    action: str  # "create", "update", "delete", "approve", "deny", "trigger"
    resource_type: str  # "order", "position", "config", "killswitch"
    resource_id: str  # Order ID, position ID, config path, etc.
    before_state: dict[str, Any] | None  # State before action (JSON)
    after_state: dict[str, Any] | None  # State after action (JSON)
    metadata: dict[str, Any]  # Additional context
    checksum: str  # SHA256 of serialized event (tamper detection)

@dataclass(frozen=True)
class ReplaySession:
    """Replay validation session."""
    session_id: str  # UUID
    start_ts_ns: int
    end_ts_ns: int
    journals_replayed: list[str]  # Paths to journal files
    events_processed: int
    events_validated: int
    discrepancies: list[str]  # List of discrepancy descriptions
    status: Literal["running", "completed", "failed"]
    checksum: str  # SHA256 of all replayed events

@dataclass(frozen=True)
class OrderBookSnapshot:
    """Point-in-time order book state."""
    timestamp_ns: int
    symbol: str
    bids: list[tuple[float, float]]  # [(price, quantity), ...]
    asks: list[tuple[float, float]]  # [(price, quantity), ...]
    sequence_number: int  # Exchange sequence number
    checksum: str  # SHA256 of snapshot (integrity validation)
```

**Files:**
- `compliance/contracts.py` (120 LOC)
- `tests/test_audit_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- Checksum calculation deterministic (same input → same checksum)
- Validation: event_type/action enums valid, checksums non-empty
- `make fmt lint type test` green

---

### Phase 12.1 — Immutable Audit Logger 📋
**Status:** Planned
**Dependencies:** 12.0 (Audit Contracts)
**Task:** Append-only audit log writer with tamper detection

**Behavior:**
- Write audit events to append-only NDJSON files
- Separate audit log: `var/log/njord/audit.ndjson`
- Calculate SHA256 checksum for each event
- Maintain running checksum chain (each event includes prior checksum)
- **Immutability: File opened in append mode only** (no overwrite, no delete)
- Rotation handled externally (logrotate or similar)
- No buffering (immediate flush to disk)

**API:**
```python
class AuditLogger:
    def __init__(
        self,
        log_path: Path = Path("var/log/njord/audit.ndjson"),
        verify_chain: bool = True,
        loop: asyncio.AbstractEventLoop | None = None
    ): ...

    async def log_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> AuditEvent:
        """Log immutable audit event asynchronously.

        Behavior:
            - Uses background executor for file writes (non-blocking)
            - Flushes after each append (fsync)

        Returns:
            AuditEvent with calculated checksum
        """
        pass

    def calculate_checksum(self, event: AuditEvent) -> str:
        """Calculate SHA256 checksum of event.

        Includes:
            - All event fields except checksum itself
            - Prior event checksum (chain validation)
        """
        pass

    def verify_chain(self, events: list[AuditEvent]) -> bool:
        """Verify audit log chain integrity.

        Returns:
            True if chain intact, False if tampering detected
        """
        pass

    async def read_events(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None,
        event_type: str | None = None
    ) -> list[AuditEvent]:
        """Read audit events asynchronously with optional filtering."""
        pass
```

**Checksum Chain Example:**
```
Event 1: checksum = SHA256(event_1_data + "")
Event 2: checksum = SHA256(event_2_data + event_1_checksum)
Event 3: checksum = SHA256(event_3_data + event_2_checksum)
```

**Files:**
- `compliance/audit_logger.py` (180 LOC)
- `tests/test_audit_logger.py`

**Acceptance:**
- Writes events to `var/log/njord/audit.ndjson` (append-only)
- Checksum chain verification works (detects tampering)
- **Test verifies tamper detection** (modify event, verify fails)
- **Test verifies append-only** (cannot open in write mode)
- No buffering (fsync after each write)
- Read events with filtering (time range, event type)
- `make fmt lint type test` green

---

### Phase 12.2 — Service Instrumentation (Audit Hooks) 📋
**Status:** Planned
**Dependencies:** 12.1 (Immutable Audit Logger)
**Task:** Instrument core services with audit logging

**Behavior:**
- Add audit logging to critical operations across services
- Emit audit events for: orders, fills, risk decisions, config changes, kill-switch trips
- Include before/after state for all mutations
- **Performance: Async audit logging** (non-blocking)
- **Fallback: Log to stderr if audit logger unavailable** (no service failure)

**Instrumentation Points:**

**Risk Engine:**
```python
# Before/after for risk decisions
await audit_logger.log_event(
    event_type="risk_decision",
    actor="risk_engine",
    action="approve" if allowed else "deny",
    resource_type="order_intent",
    resource_id=intent.intent_id,
    before_state={"intent": intent.to_dict()},
    after_state={"decision": decision.to_dict()},
    metadata={"reason": decision.reason}
)
```

**Paper Trader / Broker:**
```python
# Order placement
await audit_logger.log_event(
    event_type="order",
    actor=f"broker_{venue}",
    action="create",
    resource_type="order",
    resource_id=order.client_order_id,
    before_state=None,
    after_state=order.to_dict(),
    metadata={"venue": venue, "symbol": order.symbol}
)
```

**Config Hot-Reload:**
```python
# Config changes
await audit_logger.log_event(
    event_type="config_change",
    actor="controller",
    action="reload",
    resource_type="config",
    resource_id=config_path.name,
    before_state={"hash": old_hash},
    after_state={"hash": new_hash},
    metadata={"path": str(config_path)}
)
```

**Kill Switch:**
```python
# Kill switch trips
await audit_logger.log_event(
    event_type="killswitch",
    actor="system",
    action="trigger",
    resource_type="killswitch",
    resource_id="global",
    before_state={"active": False},
    after_state={"active": True},
    metadata={"trigger_source": source}
)
```

**Files:**
- Update `apps/risk_engine/main.py` (+30 LOC)
- Update `apps/paper_trader/main.py` (+30 LOC)
- Update `apps/broker_binanceus/main.py` (+30 LOC)
- Update `controller/config_reloader.py` (+20 LOC)
- Update `core/kill_switch.py` (+20 LOC)
- `tests/test_audit_instrumentation.py`

**Acceptance:**
- Risk decisions logged with before/after state
- Orders logged (create, cancel, fill)
- Config changes logged with file hash
- Kill-switch events logged
- Async logging (non-blocking service operations)
- Fallback to stderr if audit logger fails
- Test verifies audit events emitted for each operation
- `make fmt lint type test` green

---

### Phase 12.3 — Deterministic Replay Engine 📋
**Status:** Planned
**Dependencies:** 12.2 (Service Instrumentation)
**Task:** Replay journal events and validate against audit log

**Behavior:**
- Read journals (OHLCV, trades, fills, orders, risk decisions)
- Replay events in chronological order
- Re-execute business logic (risk checks, fill simulation)
- Compare replayed state against audit log
- Detect discrepancies (missing events, state mismatches)
- Generate replay validation report

**API:**
```python
class ReplayEngine:
    def __init__(
        self,
        journal_dir: Path,
        audit_log_path: Path,
        config: Config
    ): ...

    async def replay_session(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        journals: list[str] | None = None  # Default: all journals
    ) -> ReplaySession:
        """Replay events and validate against audit log.

        Returns:
            ReplaySession with validation results
        """
        pass

    async def replay_event(self, event: dict[str, Any]) -> Any:
        """Replay single event (re-execute business logic)."""
        pass

    def validate_state(
        self,
        replayed_state: dict[str, Any],
        audit_state: dict[str, Any]
    ) -> list[str]:
        """Compare replayed vs. audit state.

        Returns:
            List of discrepancies (empty if match)
        """
        pass

    def generate_report(self, session: ReplaySession) -> str:
        """Generate human-readable validation report."""
        pass
```

**Replay Flow:**
1. Load journals (trades, orders, fills, risk decisions)
2. Sort events by timestamp_ns
3. For each event:
   - Replay event (re-execute logic)
   - Load corresponding audit event
   - Compare replayed state vs. audit state
   - Record discrepancies
4. Generate validation report

**Files:**
- `compliance/replay_engine.py` (300 LOC)
- `tests/test_replay_engine.py`

**Acceptance:**
- Replays events from journals in chronological order
- Re-executes risk checks (deterministic)
- Compares replayed fills vs. audit log fills
- Detects discrepancies (missing events, state mismatches)
- **Test verifies perfect replay** (no discrepancies for golden journals)
- **Test verifies discrepancy detection** (inject mismatch, report shows it)
- Generate report with discrepancy details
- `make fmt lint type test` green

---

### Phase 12.4 — Order Book Reconstruction 📋
**Status:** Planned
**Dependencies:** 12.3 (Deterministic Replay Engine)
**Task:** Reconstruct historical order book from market data journals

**Behavior:**
- Read market data journals (trades, order book snapshots)
- Rebuild order book state at any timestamp
- Validate reconstructed book against exchange snapshots
- Detect gaps (missing data, sequence number jumps)
- Calculate book statistics (spread, depth, imbalance)

**API:**
```python
class OrderBookReconstructor:
    def __init__(
        self,
        journal_dir: Path,
        symbol: str
    ): ...

    async def reconstruct_at_time(
        self,
        timestamp_ns: int
    ) -> OrderBookSnapshot:
        """Reconstruct order book state at specific time.

        Returns:
            OrderBookSnapshot with bids/asks/checksum
        """
        pass

    async def replay_book_updates(
        self,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> list[OrderBookSnapshot]:
        """Replay order book updates over time range.

        Returns:
            List of snapshots at each update
        """
        pass

    def validate_against_exchange(
        self,
        reconstructed: OrderBookSnapshot,
        exchange_snapshot: OrderBookSnapshot
    ) -> list[str]:
        """Validate reconstructed book vs. exchange snapshot.

        Returns:
            List of discrepancies (empty if match)
        """
        pass

    def calculate_book_stats(
        self,
        snapshot: OrderBookSnapshot
    ) -> dict[str, float]:
        """Calculate order book statistics.

        Returns:
            {"spread": ..., "bid_depth": ..., "ask_depth": ..., "imbalance": ...}
        """
        pass

    def detect_gaps(
        self,
        snapshots: list[OrderBookSnapshot]
    ) -> list[tuple[int, int]]:
        """Detect sequence number gaps.

        Returns:
            List of (expected_seq, actual_seq) tuples
        """
        pass
```

**Files:**
- `compliance/order_book.py` (250 LOC)
- `tests/test_order_book_reconstruction.py`

**Acceptance:**
- Reconstructs order book at any timestamp
- Validates against exchange snapshots
- **Test verifies reconstruction accuracy** (compare vs. golden snapshots)
- Detects sequence number gaps
- Calculates book statistics (spread, depth, imbalance)
- **Test verifies gap detection** (inject missing sequence, detect it)
- `make fmt lint type test` green

---

### Phase 12.5 — Audit Report Generator 📋
**Status:** Planned
**Dependencies:** 12.4 (Order Book Reconstruction)
**Task:** Generate comprehensive audit reports for compliance

**Behavior:**
- Generate daily/weekly/monthly audit summaries
- Include: order count, fill count, risk rejections, config changes, kill-switch events
- Calculate metrics: order-to-fill ratio, rejection rate, config change frequency
- Export to CSV, JSON, HTML formats
- Include checksum verification results

**Report Types:**

**1. Daily Trading Summary**
- Orders placed (count, total notional)
- Fills executed (count, total notional, avg slippage)
- Risk rejections (count, breakdown by reason)
- Kill-switch events (count, duration)
- Config changes (count, list of files)

**2. Audit Trail Verification**
- Total audit events
- Checksum chain status (intact/tampered)
- Replay validation results (discrepancies count)
- Missing events (expected vs. actual)

**3. Order Book Quality**
- Reconstruction success rate
- Sequence gaps detected
- Average spread by symbol
- Book depth percentiles

**API:**
```python
class AuditReportGenerator:
    def __init__(
        self,
        audit_log_path: Path,
        journal_dir: Path
    ): ...

    def generate_daily_summary(
        self,
        date: str  # YYYY-MM-DD
    ) -> dict[str, Any]:
        """Generate daily trading summary.

        Returns:
            Summary dict with all metrics
        """
        pass

    def generate_audit_verification(
        self,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> dict[str, Any]:
        """Generate audit trail verification report.

        Returns:
            Verification status with checksum results
        """
        pass

    def generate_order_book_quality(
        self,
        symbol: str,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> dict[str, Any]:
        """Generate order book quality report.

        Returns:
            Quality metrics (gaps, spread, depth)
        """
        pass

    def export_to_csv(
        self,
        report: dict[str, Any],
        output_path: Path
    ) -> None:
        """Export report to CSV."""
        pass

    def export_to_html(
        self,
        report: dict[str, Any],
        output_path: Path
    ) -> None:
        """Export report to interactive HTML."""
        pass
```

**Files:**
- `compliance/report_generator.py` (280 LOC)
- `compliance/templates/audit_report.html` (embedded)
- `tests/test_report_generator.py`

**Acceptance:**
- Generates daily trading summaries
- Generates audit verification reports
- Generates order book quality reports
- Exports to CSV, JSON, HTML
- **Test verifies report accuracy** (compare vs. known event counts)
- HTML report includes interactive charts
- `make fmt lint type test` green

---

### Phase 12.6 — Compliance CLI 📋
**Status:** Planned
**Dependencies:** 12.5 (Audit Report Generator)
**Task:** CLI for audit operations and compliance tasks

**Behavior:**
- Verify audit log integrity (checksum chain)
- Replay events for validation
- Reconstruct order book at timestamp
- Generate audit reports
- Search audit log by criteria
- Export audit events

**CLI Commands:**
```bash
# Verify audit log integrity
python -m compliance.cli verify \
    --audit-log var/log/njord/audit.ndjson \
    --start-date 2025-01-01 \
    --end-date 2025-01-31

# Replay events
python -m compliance.cli replay \
    --start-ts 1234567890000000000 \
    --end-ts 1234567890999999999 \
    --journals var/log/njord/

# Reconstruct order book
python -m compliance.cli reconstruct-book \
    --symbol BTC/USDT \
    --timestamp 1234567890000000000

# Generate report
python -m compliance.cli report \
    --type daily \
    --date 2025-01-15 \
    --output audit_report.html

# Search audit log
python -m compliance.cli search \
    --event-type order \
    --actor risk_engine \
    --start-date 2025-01-01

# Export audit events
python -m compliance.cli export \
    --format csv \
    --start-date 2025-01-01 \
    --output audit_events.csv
```

**API:**
```python
class ComplianceCLI:
    def __init__(
        self,
        audit_log_path: Path,
        journal_dir: Path
    ): ...

    async def verify_integrity(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> None:
        """Verify audit log checksum chain."""
        pass

    async def replay_events(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        journals: list[str] | None = None
    ) -> None:
        """Replay events and display validation results."""
        pass

    async def reconstruct_book(
        self,
        symbol: str,
        timestamp_ns: int
    ) -> None:
        """Reconstruct and display order book."""
        pass

    async def generate_report(
        self,
        report_type: str,
        date: str | None = None,
        output_path: Path | None = None
    ) -> None:
        """Generate and save audit report."""
        pass

    async def search_audit_log(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> None:
        """Search audit log and display results."""
        pass

    async def export_events(
        self,
        format: str,  # csv, json, ndjson
        output_path: Path,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> None:
        """Export audit events to file."""
        pass
```

**Files:**
- `compliance/cli.py` (300 LOC)
- `tests/test_compliance_cli.py`

**Acceptance:**
- Verify command detects checksum tampering
- Replay command shows discrepancies
- Reconstruct command displays order book
- Report command generates HTML/CSV/JSON
- Search command filters by criteria
- Export command produces valid output files
- All commands have --help text
- `make fmt lint type test` green

---

### Phase 12.7 — Regulatory Export Templates 📋
**Status:** Planned
**Dependencies:** 12.6 (Compliance CLI)
**Task:** Pre-formatted export templates for regulatory reporting

**Behavior:**
- Define export schemas for common regulatory formats
- FIX protocol message export (orders, fills)
- Trade blotter export (CSV with required fields)
- Position reconciliation report
- Daily activity summary (regulatory format)

**Export Templates:**

**1. FIX Protocol Messages**
```python
# Export orders/fills in FIX 4.4 format
def export_fix_messages(
    events: list[AuditEvent],
    output_path: Path
) -> None:
    """Export as FIX 4.4 messages."""
    # Format: 8=FIX.4.4|9=...|35=D|...
    pass
```

**2. Trade Blotter (CSV)**
```csv
Date,Time,Symbol,Side,Quantity,Price,Commission,OrderID,FillID,Venue
2025-01-15,09:30:15.123,BTC/USDT,BUY,0.5,45000.00,22.50,ord_123,fill_456,binanceus
```

**3. Position Reconciliation**
```csv
Symbol,OpenQty,AvgPrice,CurrentPrice,UnrealizedPnL,RealizedPnL
BTC/USDT,0.5,45000.00,46000.00,500.00,0.00
```

**4. Daily Activity Summary**
```json
{
  "date": "2025-01-15",
  "firm_id": "NJORD",
  "orders_placed": 150,
  "orders_filled": 142,
  "orders_cancelled": 8,
  "total_buy_notional": 1500000.00,
  "total_sell_notional": 1480000.00,
  "net_position_change": 20000.00,
  "risk_rejections": 5
}
```

**API:**
```python
class RegulatoryExporter:
    def __init__(
        self,
        audit_log_path: Path,
        journal_dir: Path
    ): ...

    def export_fix_messages(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        output_path: Path
    ) -> None:
        """Export orders/fills as FIX 4.4 messages."""
        pass

    def export_trade_blotter(
        self,
        date: str,  # YYYY-MM-DD
        output_path: Path
    ) -> None:
        """Export daily trade blotter (CSV)."""
        pass

    def export_position_reconciliation(
        self,
        timestamp_ns: int,
        output_path: Path
    ) -> None:
        """Export position reconciliation report."""
        pass

    def export_daily_activity_summary(
        self,
        date: str,
        output_path: Path
    ) -> None:
        """Export daily activity summary (JSON)."""
        pass
```

**Files:**
- `compliance/regulatory_export.py` (220 LOC)
- `tests/test_regulatory_export.py`

**Acceptance:**
- FIX messages valid (parseable by FIX parser)
- Trade blotter includes all required fields
- Position reconciliation matches backtest results
- Daily activity summary accurate
- **Test verifies FIX format validity**
- **Test verifies CSV field completeness**
- `make fmt lint type test` green

---

### Phase 12.8 — Audit Service Daemon 📋
**Status:** Planned
**Dependencies:** 12.7 (Regulatory Export Templates)
**Task:** Long-running service for real-time audit logging

**Behavior:**
- Subscribe to all audit-relevant topics (orders, fills, risk decisions, config changes)
- Write events to immutable audit log in real-time
- Expose audit query API (HTTP `/audit/events`, `/audit/verify`)
- Health check endpoint (HTTP `/health`)
- **Bind to localhost by default** (127.0.0.1:9093)
- **Production gating: Require `NJORD_ENABLE_AUDIT=1` env var before routing events** (health check still served)
- Graceful shutdown (SIGTERM handling)

**API:**
```python
class AuditService:
    def __init__(
        self,
        config: Config,
        bus: BusProto,
        audit_logger: AuditLogger,
        bind_host: str = "127.0.0.1",
        port: int = 9093
    ): ...

    async def start(self) -> None:
        """Start audit service.

        Tasks:
            - Check `NJORD_ENABLE_AUDIT=1` (exit early if disabled)
            - Subscribe to audit-relevant topics
            - Start real-time audit logging
            - Expose HTTP API for queries
            - Expose health check endpoint
        """
        pass

    async def handle_event(self, topic: str, event: dict[str, Any]) -> None:
        """Handle incoming event and log to audit."""
        pass

    async def query_events(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None,
        event_type: str | None = None,
        actor: str | None = None
    ) -> list[AuditEvent]:
        """Query audit events via HTTP API."""
        pass

    async def verify_integrity(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> dict[str, Any]:
        """Verify audit log integrity via HTTP API.

        Returns:
            {"status": "intact|tampered", "events_verified": N, "discrepancies": [...]}
        """
        pass
```

**HTTP Endpoints:**
```
GET  /audit/events?start_ts=...&end_ts=...&event_type=...&actor=...
GET  /audit/verify?start_ts=...&end_ts=...
GET  /health
```

**Files:**
- `apps/audit_service/main.py` (180 LOC)
- `tests/test_audit_service.py`

**Acceptance:**
- Subscribes to audit-relevant topics
- Logs events in real-time (async, non-blocking)
- Query API returns filtered events
- Verify API detects tampering
- Health check accessible at `http://localhost:9093/health`
- **Security: Binds to localhost (127.0.0.1) by default**
- **Audit routing gated by `NJORD_ENABLE_AUDIT=1` env var** (disabled by default)
- **Test verifies service exits early when audit disabled (health check only)**
- Graceful shutdown on SIGTERM
- Test includes end-to-end audit flow (event → log → query)
- `make fmt lint type test` green

---

### Phase 12.9 — Compliance Documentation 📋
**Status:** Planned
**Dependencies:** 12.8 (Audit Service Daemon)
**Task:** Comprehensive documentation for compliance and audit system

**Deliverables:**

**1. Audit System Architecture (docs/compliance/ARCHITECTURE.md)**
- Component diagram (AuditLogger, ReplayEngine, OrderBookReconstructor)
- Data flow: Event → Audit Log → Verification → Report
- Checksum chain mechanics
- Immutability guarantees

**2. Audit Trail Guide (docs/compliance/AUDIT_TRAIL.md)**
- Event types and schemas
- Checksum calculation details
- Tamper detection mechanics
- Best practices for log retention

**3. Replay Validation Guide (docs/compliance/REPLAY.md)**
- Replay engine usage
- Discrepancy interpretation
- Resolution procedures
- Example replay scenarios

**4. Regulatory Export Guide (docs/compliance/REGULATORY.md)**
- FIX message export
- Trade blotter format
- Position reconciliation
- Daily activity summary
- Compliance workflows

**5. Operations Runbook (docs/compliance/RUNBOOK.md)**
- Starting audit service
- Running integrity checks
- Generating audit reports
- Troubleshooting discrepancies
- Emergency procedures (log corruption, tampering detection)

**6. API Reference (docs/compliance/API.md)**
- AuditLogger API
- ReplayEngine API
- OrderBookReconstructor API
- RegulatoryExporter API
- CLI command reference
- HTTP API reference

**Files:**
- `docs/compliance/ARCHITECTURE.md`
- `docs/compliance/AUDIT_TRAIL.md`
- `docs/compliance/REPLAY.md`
- `docs/compliance/REGULATORY.md`
- `docs/compliance/RUNBOOK.md`
- `docs/compliance/API.md`

**Acceptance:**
- Architecture diagram shows all components
- Audit trail guide includes checksum examples
- Replay guide includes 3+ example scenarios
- Regulatory guide covers all export formats
- Runbook includes troubleshooting steps
- API reference documents all public interfaces
- All docs use consistent formatting (markdown)
- `make fmt lint type test` green (no code changes)

---

## Dependencies Summary

```
Phase 11 (Monitoring & Alerts) ✅
    └─> Phase 12.0 (Audit Contracts) — AuditEvent, ReplaySession, OrderBookSnapshot
            └─> 12.1 (Immutable Audit Logger) — Append-only logging, checksum chain
                    └─> 12.2 (Service Instrumentation) — Audit hooks in services
                            └─> 12.3 (Deterministic Replay Engine) — Validation against audit log
                                    └─> 12.4 (Order Book Reconstruction) — Historical book state
                                            └─> 12.5 (Audit Report Generator) — Compliance reports
                                                    └─> 12.6 (Compliance CLI) — Management commands
                                                            └─> 12.7 (Regulatory Export) — FIX, CSV, JSON formats
                                                                    └─> 12.8 (Audit Service) — Real-time daemon
                                                                            └─> 12.9 (Documentation) — Guides and API reference
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---
