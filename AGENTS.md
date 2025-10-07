# Njord Quant — Agent Operating Guide

## Mission Statement

Implement a **robust, research-driven algorithmic trading framework** for cryptocurrency markets in **16 incremental phases**. Each phase delivers small, reviewable diffs (≤150 LOC / ≤4 files) that maintain 100% green guardrails: formatted, linted, typed, and tested.

**Current Status:** Phase 8 complete — Execution Layer fully operational
**Target:** Phase 16 — Production-ready autonomous trading system

## Documentation Hierarchy

This project maintains three levels of agent guidance:

1. **[AGENTS.md](./AGENTS.md)** (this file) — Strategic operating procedures, coding standards, and principles
2. **[ROADMAP.md](./ROADMAP.md)** — Tactical task-level instructions for each phase/sub-phase
3. **[CLAUDE.md](./CLAUDE.md)** — Claude Code entry point (references this file)

**For task execution:** Always consult roadmap phase-specific files for detailed behavioral specifications, acceptance criteria, and file locations. AGENTS.md defines *how* we build; roadmap/phases/*.md files define *what* to build next.

**Roadmap Structure (Updated 2025-10-02):**
- `ROADMAP.md` — Lightweight index (~170 lines) with phase table
- `roadmap/phases/phase-XX-name.md` — Detailed phase specifications (400-1500 lines each)
- Token efficiency: Read index + specific phase = ~2000 lines vs 9000 (78% savings)

---

## Top-Level SOPs (Strategic Operating Procedures)

### 1. Scope & Boundaries
- **Purpose:** Research → backtesting → paper trading → live trading pipeline
- **Exchange:** Binance.US (via CCXT Pro) with multi-exchange extensibility
- **Non-negotiables:**
  - Risk caps and kill-switch protections are **never bypassed**
  - **Never commit secrets** — `config/secrets.enc.yaml` stays encrypted
  - Production environment requires explicit flags (`env=live` + `NJORD_ENABLE_LIVE=1`)
  - Observability/alerting/audit services remain disabled unless their gating env vars are set (`NJORD_ENABLE_METRICS`, `NJORD_ENABLE_ALERTS`, `NJORD_ENABLE_AUDIT`)
  - Each phase **must not break prior phases** — earlier tests must remain green

### 2. Iteration Discipline
- **Atomic commits:** ≤150 lines of code, ≤4 files per commit
- **Green code mandate:** After every change, run:
  ```bash
  make fmt && make lint && make type && make test
  ```
- **Failure protocol:** If any check fails → **fix and rerun until all pass**
- **Output format:**
  - **During iteration:** Minimal diffs only (no explanations)
  - **Final output:** Structured format with verification results (see Communication Protocol)
  - **Debugging:** Verbose explanations only when explicitly requested
- **Performance guardrail:** Test suite must complete in ≤30s; no long sleeps or unbounded loops
- **Test tiering:**
  - **Unit tests (default):** Use `InMemoryBus` or mocks; no network I/O; always fast; required for all commits
  - **Integration tests (when critical):** Localhost Redis via Docker Compose; gated with `@pytest.mark.integration` or `REDIS_SKIP=1`; required when acceptance criteria depend on Redis pub/sub behavior
  - **Security:** Integration tests must bind to 127.0.0.1 only (no external network); use `docker-compose.test.yml`

### 3. Coding Standards
| Standard | Specification |
|----------|---------------|
| **Python version** | 3.11 |
| **Type checking** | `mypy --strict` |
| **Formatting** | `ruff format` |
| **Linting** | `ruff check .` (rules: E, F, I, B, UP, SIM, RUF) |
| **Testing** | `pytest` (two-tier strategy: unit tests with `InMemoryBus`, integration tests with localhost Redis) |
| **Import style** | `from core.contracts import X` (never top-level `contracts`) |

### 4. Repository Structure
```
njord_quant/
├── config/          # YAML configs (base.yaml, secrets.enc.yaml)
├── core/            # Framework primitives (bus, broker, contracts, logging)
├── apps/            # Service daemons (md_ingest, risk_engine, broker_binanceus, etc.)
├── strategies/      # Trading strategy plugins
├── execution/       # Execution algorithms (TWAP, VWAP, Iceberg, POV, slippage models)
├── research/        # Research API (data_reader.py, analysis tools)
├── risk/            # Risk rule modules
├── backtest/        # Replay engine and metrics
├── roadmap/         # Phase specifications and task tracking
│   └── phases/      # Detailed phase specifications (phase-XX-name.md)
├── tests/           # Unit, integration, and golden tests
│   ├── unit/
│   ├── integration/
│   └── golden/
├── var/
│   ├── log/njord/   # NDJSON structured logs (via structlog)
│   └── state/       # Stateful watermarks and checkpoints
├── deploy/systemd/  # Service unit files
└── scripts/         # Operational scripts (kill switch, roadmap navigation, etc.)
```

### 5. Logging & Journaling
- **Format:** NDJSON via `structlog` → `var/log/njord/`
- **Journals:** Append-only NDJSON (rotation handled externally, not inline)
- **Topics:** Redis pub/sub for event streaming (`md.trades.{symbol}`, `risk.decisions`, etc.)
- **Log Levels:**
  - Development: DEBUG (verbose, all operations)
  - Production: INFO (operational events, warnings, errors)
  - Critical services: Structured logging with request IDs
- **Retention Policy:**
  - Development logs: 7 days
  - Production logs: 30 days (operational), 1 year (compliance/audit)
  - Journals: Indefinite (append-only, archived after 90 days)
- **Rotation:** External (logrotate), size-based (100MB per file) or daily
- **NEVER log:**
  - API keys, passwords, tokens
  - PII (email addresses, user IDs in plaintext)
  - Secrets from `config/secrets.enc.yaml`
  - Full order book depth (only top N levels)

### 6. Commit Conventions
**Format:** Conventional Commits (NO AI attribution or watermarks)
```
<type>(<scope>): <subject>

Examples:
feat(core/logging): structured JSON logging helper + snapshot test
fix(broker): handle duplicate clientOrderId with idempotency
test(paper_trader): add position math partial close scenario
chore(mypy): exclude app __main__ entrypoints temporarily
```

**CRITICAL:** Do NOT add AI watermarks, attribution footers, or "Generated by" tags.
This is a professional production codebase. Commits must look like human team members wrote them.

```
❌ PROHIBITED:
🤖 Generated with [Claude Code](...)
Co-Authored-By: Claude <...>
Generated by AI
```

---

## Phase Roadmap (0 → 16)

### **Phase 0** — Bootstrap & Guardrails ✅
- Config loader (Pydantic)
- Structured JSON logging (`structlog`)
- NDJSON journal primitives
- Secrets management (`sops` placeholder)

### **Phase 1** — Event Bus & Market Data Ingest ✅
- Async Redis pub/sub (`core/bus.py`)
- Trade/book/ticker contracts
- CCXT Pro market data daemon (`apps/md_ingest`)
- Reconnect/backoff logic with deduplication

### **Phase 2** — Risk Engine MVP & Paper OMS ✅
- Risk engine: notional caps, daily loss limits, rate guards
- Paper trader: simulated fills with position tracking
- Kill-switch (file + Redis) integration
- Idempotency checks (intent deduplication)

### **Phase 3** — Strategy Plugin Framework ✅
- Strategy base class with `on_event()` hook
- Strategy context (injected state container)
- Strategy registry (discovery + factory)
- Strategy manager (lifecycle management)
- Config-driven strategy loading
- Sample strategies: trendline_break, rsi_tema_bb
- Golden tests for deterministic validation

### **Phase 4** — Market Data Storage ✅
- Persist OHLCV + tick streams to disk
- Compression (gzip/lz4)
- Rotation policy
- Replay hooks for backtesting

### **Phase 5** — Backtester ✅
- Deterministic event replay
- Golden equity curve validation
- Parameter sweep harness

### **Phase 6** — Portfolio Allocator ✅
- Multi-strategy capital allocation
- Risk-weighted rebalancing
- Kill-switch integration

### **Phase 7** — Research API ✅
- Pandas/PyArrow data interface
- Jupyter notebook integration (offline only)
- **Dependencies:** pandas, pyarrow, matplotlib, jupyter (optional install group)

### **Phase 8** — Execution Layer ✅
- Phase 8.0: Execution foundations (BusProto, BaseExecutor, sync/async adapters)
- Execution algorithms: TWAP, VWAP, Iceberg, POV
- Slippage models (linear, square-root)
- Smart order router with algorithm selection
- Execution simulator (backtest integration)
- Execution performance metrics (implementation shortfall, benchmark comparisons)
- **Architecture:** All executors emit OrderIntent → Risk Engine → Broker (no bypass)

### **Phase 9** — Metrics & Telemetry 📋
- Prometheus metrics exporter with HTTP /metrics endpoint
- Service instrumentation (risk_engine, paper_trader, broker, strategies)
- Grafana dashboard configs (system health, trading, performance, execution)
- Metric aggregation service with downsampling and persistence
- Performance attribution (Brinson, factor-based, risk-adjusted)
- Real-time metrics dashboard (WebSocket/SSE)
- Alert system with YAML-defined rules
- Metrics retention and cleanup
- **No runtime dependencies** (Prometheus/Grafana deployment-only)
- **Performance:** <1% overhead, cardinality bounded

### **Phase 10** — Live Trade Controller 📋
- Unified CLI: `njord-ctl start|stop|restart|reload|status|logs|session`
- Service registry with auto-discovery and dependency ordering
- Process manager (start/stop/restart with PID tracking, SIGTERM → SIGKILL)
- Config hot-reload (SHA256 hash, Redis pub/sub signal, no restart)
- Session manager (UUID session_id, NDJSON journaling, config hash tracking)
- Health checks (HTTP /health endpoints, Redis ping, auto-restart)
- Log aggregation (tail, filter, search, colorized, chronological merge)
- Controller daemon (persistent service, HTTP control API)

### **Phase 11** — Monitoring & Alerts 📋
- Alert contracts (Alert, AlertRule, NotificationChannel)
- Alert bus with routing, deduplication (Redis TTL), and rate limiting
- Rule engine with metric evaluation and duration tracking
- Notification channels: log, Redis, webhook, email (stub), Slack (stub)
- Alert service daemon with health checks and SIGTERM handling
- Alert CLI for management and testing
- **Production gating:** NJORD_ENABLE_ALERTS=1 (disabled by default)
- **Security:** Env vars for secrets, localhost binding by default (127.0.0.1:9092)
- **No runtime dependencies** (stdlib + existing stack only)

### **Phase 12** — Compliance & Audit 📋
- Immutable audit logger with checksum chaining (async, append-only)
- Service instrumentation for audit hooks (orders, fills, risk, config, kill-switch)
- Deterministic replay engine and order book reconstruction
- Regulatory exports (FIX, trade blotter, reconciliation)
- Audit service daemon (localhost-only, `NJORD_ENABLE_AUDIT` gate) + CLI & docs
- Compliance documentation: architecture, audit trail, replay, regulatory guides
- **No new runtime dependencies** (stdlib + existing stack only)
- **Graceful shutdown:** SIGTERM handling for all services

### **Phase 13** — Advanced Strategy Toolkit
- Factor models (momentum, mean reversion, carry)
- ML feature pipeline (offline training only)
- Ensemble meta-strategies

### **Phase 14** — Simulation Harness
- Multi-day replay tests
- Stress scenarios (flash crash, liquidity crunch)
- Monte Carlo batch runs

### **Phase 15** — Deployment Framework
- Systemd unit templates
- Ansible playbooks (optional)
- Config packaging (encrypted secrets via `sops`)
- Ops runbook (alerts, restart procedures)

### **Phase 16** — Optimization Pass
- CPU/memory profiling
- Latency tuning (event loop optimization)
- Code cleanup (remove dead code, consolidate duplicates)
- Documentation pass (ADRs, API docs, operator manual)

---

## Micro-Prompt Template (For Sub-Phase Tasks)

**Note:** Detailed task specifications are maintained in `roadmap/phases/phase-XX-name.md` files. This template defines the **standard structure** that all phase specifications follow. Code agents implementing a sub-phase should read the phase file and follow this structure.

### Template Structure (For Roadmap Phase Files)

When documenting sub-phase tasks in roadmap files, use this evolved template:

```markdown
### Phase <N>.<M> — <Title> <status-emoji>
**Status:** Planned | In Progress | Complete
**Dependencies:** <N>.<M-1> (Previous Task Name)
**Task:** <one-sentence summary>

**Critical Architectural Requirements:** (if applicable)
1. <Domain-specific constraint 1 (e.g., "No Risk Engine Bypass")>
2. <Domain-specific constraint 2 (e.g., "Bus Protocol Layering")>
3. <Timestamp conventions, data flow requirements, etc.>

**Deliverables:** (if complex abstractions with reference implementations)

#### 1. <Component Name>
```python
# Reference implementation showing key contracts/interfaces
class ExampleContract:
    """Docstring with warnings for dangerous operations.

    WARNING: Document failure modes, usage constraints, safety requirements.
    - Safe usage pattern 1
    - Unsafe pattern that FAILS
    - Context where this should NOT be used
    """

    def method_signature(self, args: Type) -> ReturnType:
        """Method-level documentation."""
        pass
```

#### 2. <Additional Components>
...

**API:** (alternative to Deliverables for simpler cases)
```python
class ImplementationClass:
    def __init__(self, required_params: Type): ...

    def primary_method(self, args: Type) -> ReturnType:
        """Core functionality description.

        Args:
            args: Parameter documentation

        Returns:
            Return value documentation

        Raises:
            ErrorType: When this failure occurs
        """
        pass
```

**Requirements:**
- <Functional requirement 1>
- <Functional requirement 2>
- <Data flow requirement (e.g., "Must emit OrderIntent, not call broker directly")>

**Constraints:**
- No new **runtime** dependencies (Phases 0-6, 8-16)
  - **Exception:** Phase 7 (Research API) may add pandas, pyarrow, matplotlib, jupyter (optional group)
- **Network I/O in tests:**
  - **Unit tests:** No network I/O (use `InMemoryBus` or mocks)
  - **Integration tests:** Localhost Redis permitted when critical to module behavior
    - Must use `docker-compose.test.yml` (127.0.0.1 binding only)
    - Must include skip guards (`REDIS_SKIP=1` or availability check)
    - Must mark with `@pytest.mark.integration` or document in test file
- Must stay deterministic (fixed seeds, no real sleeps, isolated test topics)
- Keep diffs minimal (≤150 LOC, ≤4 files)
- <Add phase-specific architectural constraints here>

**Files:**
- `path/to/file1.py` (description, ~LOC estimate)
- `path/to/file2.py` (description, ~LOC estimate)
- `tests/test_module.py`

**Acceptance:**
- <Behavioral assertion 1 (e.g., "Returns list[OrderIntent], NO broker calls")>
- <Behavioral assertion 2 (e.g., "Slices scheduled at correct intervals")>
- <Data integrity check (e.g., "Total quantity distributed evenly across slices")>
- <Metadata requirement (e.g., "Each OrderIntent.meta includes execution_id")>
- <Edge case handling (e.g., "Handles partial fills correctly")>
- <Test scenario 1 (e.g., "Test includes partial fill scenario")>
- <Test scenario 2 (e.g., "Test includes multiple replenishment cycles")>
- **Round-trip verification (if applicable): "Test verifies DataStructureA → Transformation → DataStructureB recovery"**
- **Critical path test: "Test verifies <architectural boundary> is enforced (e.g., no broker bypass)"**
- **Integration tests (REQUIRED for Redis pub/sub, event bus, or Redis-dependent modules):**
  - Unit tests MUST use `InMemoryBus` (no Redis dependency)
  - Integration test MUST verify Redis pub/sub round-trip (gated, localhost only)
  - Test MUST include skip guard: `if os.getenv("REDIS_SKIP") == "1": pytest.skip()`
  - Test MUST be marked: `@pytest.mark.integration`
  - Docker Compose config MUST bind to 127.0.0.1 only (verified in test)
  - Integration test MUST be run during verification and audit loops
- `make fmt lint type test` green
- **Integration tests green (if Redis-dependent module)**
- **Audit must PASS (zero High/Medium findings)**
```

---

### Code Agent Implementation Protocol

When a user says **"Implement Phase X.Y — Sub-Phase Title"**, the code agent must:

1. **Read Phase File:**
   ```bash
   # Find current phase from ROADMAP.md
   cat ROADMAP.md | grep "**Current Phase:**"

   # Read corresponding phase file
   cat roadmap/phases/phase-XX-name.md
   ```

2. **Locate Sub-Phase Section:**
   - Find `### Phase X.Y — Title` heading
   - Extract all content until next `### Phase` or `##` heading

3. **Parse and Execute:**
   - **Status/Dependencies:** Verify dependencies are ✅ complete
   - **Task:** Understand one-sentence objective
   - **Critical Architectural Requirements:** Enforce as non-negotiable constraints
   - **Deliverables/API:** Use as reference implementation guide
   - **Requirements:** Implement all functional requirements
   - **Constraints:** Enforce generic + phase-specific constraints
   - **Files:** Create/modify listed files with estimated LOC
   - **Acceptance:** Treat as executable test specification

4. **Implementation Execution:**
   ```python
   # For each file in Files section:
   #   - Create module structure
   #   - Implement contracts from Deliverables/API
   #   - Enforce Requirements and Constraints
   #   - Add inline warnings for dangerous operations

   # For test file:
   #   - Create test class
   #   - For each item in Acceptance section:
   #       - Write test_<acceptance_item>() function
   #       - Verify behavioral assertion
   #       - Cover edge cases mentioned
   #       - Implement round-trip verification if specified
   ```

5. **Verification Loop:**
   ```bash
   # Unit tests (always run)
   make fmt && make lint && make type && make test
   # If red → fix errors → rerun until green

   # Integration tests (REQUIRED for Redis-dependent modules)
   # MUST run when implementing pub/sub, event bus, or any Redis interaction
   docker-compose -f docker-compose.test.yml up -d redis
   docker-compose -f docker-compose.test.yml exec redis redis-cli ping  # Verify ready
   PYTHONPATH=. pytest -v -m integration  # Run integration-marked tests
   docker-compose -f docker-compose.test.yml down
   # If red → fix errors → rerun

   # ⚠️  CRITICAL: Do not skip integration tests for Redis modules
   # The framework is Redis-dependent - skipping tests accumulates debt

   # If all green → proceed to audit
   ```

6. **Audit Loop:** (Production Quality Gate)
   ```
   ┌─ Audit Process ────────────────────────┐
   │ 1. Run audit per AUDIT.md              │
   │ 2. High/Medium findings?               │
   │    → Make corrections                  │
   │    → Re-run affected checks:           │
   │       • Code → make fmt lint type test │
   │       • Redis modules → integration    │
   │         tests (docker-compose up +     │
   │         pytest -m integration)         │
   │       • Docs only → skip tests         │
   │    → Re-audit                          │
   │    → Loop until zero High/Medium       │
   │ 3. Low findings?                       │
   │    → Present to user (apply/defer)     │
   │ 4. Audit PASS → proceed to commit      │
   └────────────────────────────────────────┘
   ```

7. **Output Format:**
   - **Unified diff only** (no prose explanations unless debugging)
   - Include file paths and line numbers
   - Commit message following conventional commits
   - Include "Audit: PASS" in commit body

---

### Acceptance Criteria Specification Guidelines

**Acceptance criteria must be executable test specifications.** Each acceptance item should map to one or more test assertions:

#### Pattern 1: Behavioral Assertion
```markdown
**Acceptance:**
- Returns list[OrderIntent], NO broker calls
```
**Test Implementation:**
```python
def test_twap_returns_intents_no_broker_calls(mock_broker):
    executor = TWAPExecutor(strategy_id="test")
    intents = executor.plan_execution(algo)
    assert isinstance(intents, list)
    assert all(isinstance(i, OrderIntent) for i in intents)
    mock_broker.place.assert_not_called()  # NO broker calls
```

#### Pattern 2: Edge Case Coverage
```markdown
**Acceptance:**
- Test includes partial fill scenario
```
**Test Implementation:**
```python
def test_twap_handles_partial_fills():
    executor = TWAPExecutor(strategy_id="test")
    intents = executor.plan_execution(algo)
    # Simulate partial fill on first slice
    fills = simulate_fills(intents, fill_ratio=0.5)
    report = executor.build_report(fills)
    assert report.filled_quantity == algo.total_quantity * 0.5
    assert report.status == "running"  # Not completed
```

#### Pattern 3: Round-Trip Verification
```markdown
**Acceptance:**
- Test verifies OrderIntent.meta → FillEvent → ExecutionReport round-trip
```
**Test Implementation:**
```python
def test_execution_metadata_round_trip():
    executor = TWAPExecutor(strategy_id="test")
    intents = executor.plan_execution(algo)

    # Extract metadata from intent
    execution_id = intents[0].meta["execution_id"]
    slice_id = intents[0].meta["slice_id"]

    # Simulate fill with metadata
    fill = FillEvent(
        client_order_id=intents[0].intent_id,
        execution_id=execution_id,  # Must recover from OrderIntent
        ...
    )

    # Build report from fills
    report = executor.build_report([fill])
    assert report.execution_id == execution_id  # Round-trip verified
```

#### Pattern 4: Architectural Boundary Enforcement
```markdown
**Acceptance:**
- **CRITICAL: Child OrderIntents must pack execution_id into OrderIntent.meta**
- **Test verifies no direct broker calls**
```
**Test Implementation:**
```python
def test_executor_enforces_risk_engine_flow(mock_broker):
    executor = TWAPExecutor(strategy_id="test")
    intents = executor.plan_execution(algo)

    # Verify metadata structure
    for intent in intents:
        assert "execution_id" in intent.meta
        assert "slice_id" in intent.meta

    # Verify no bypass
    mock_broker.place.assert_not_called()
```

---

### Example: Well-Formed Sub-Phase Specification

See `roadmap/phases/phase-08-execution.md` Phase 8.2 (TWAP Algorithm) for reference implementation of this template with:
- ✅ Dependencies tracking
- ✅ Critical architectural requirements
- ✅ API reference implementation with warnings
- ✅ Explicit test scenario coverage
- ✅ Round-trip verification requirements
- ✅ Behavioral assertions mapped to tests

---

## Quick Fix Patterns (Common Issues)

### Linting
| Error Code | Fix Pattern |
|------------|-------------|
| **I001** | Sort imports: stdlib → third-party → local |
| **RUF022** | Add `__all__` to `__init__.py` or sort existing |
| **E501** | Already ignored in `ruff.toml` |
| **B027** | Replace empty abstract methods with concrete no-ops or state flags |

### Type Checking
| Issue | Fix Pattern |
|-------|-------------|
| Missing annotations | Add return types: `-> None`, `-> int`, etc. |
| Optional ambiguity | Prefer `X | None` (Python 3.11 union syntax) |
| Protocol mismatch | Ensure protocol methods match signature exactly |
| `Any` overuse | Prefer concrete types; use `Any` only as last resort |

### Test Determinism
| Issue | Fix Pattern |
|-------|-------------|
| Time-dependent tests | Inject `FixedClock` into `Context` |
| Random flakiness | Seed RNG: `random.seed(42)` |
| Async race conditions | Use `asyncio.Event` or `wait_for()` helpers |
| Network dependency | Mock external calls or skip with `@pytest.mark.skipif` |
| Golden test bloat | Keep golden tests ≤1k JSONL lines; compress or split if needed |

### Import Organization
```python
# Correct order:
import asyncio                    # stdlib
import time
from pathlib import Path

import structlog                  # third-party
from redis.asyncio import Redis

from core.bus import Bus          # local (alphabetical)
from core.config import Config
from core.contracts import OrderIntent
```

---

## Agent Directives (Critical Rules)

1. **Always run tests before emitting output**
   ```bash
   make fmt && make lint && make type && make test
   ```

2. **If failing: iterate until green**
   - Do not emit partial or broken diffs
   - Fix errors in sequence: fmt → lint → type → test
   - Use `pytest -xvs` for detailed failure output

3. **If blocked: propose smallest unblocking change**
   - State the blocker explicitly
   - Provide minimal diff to unblock (e.g., stub a dependency)
   - Resume main task after unblock

4. **Output format: diffs only (unless debug requested)**
   - Use unified diff format (patch)
   - Include file paths and line numbers
   - No explanatory prose in standard output

5. **Respect architectural boundaries**
   - Strategies emit `OrderIntent` → Risk Engine → Broker
   - Never let strategies call broker directly
   - Never bypass risk checks or kill-switch

6. **Security hygiene**
   - Never log secrets (API keys, passwords)
   - Never commit `config/secrets.enc.yaml` contents
   - Use environment variables for sensitive runtime config

7. **Determinism over convenience**
   - Tests must pass consistently (no flaky tests)
   - Use fixed seeds for random operations
   - Inject time/clock dependencies for testing

---

## Escalation & Recovery Protocols

### Regression Detection & Rollback
**Trigger:** Phase N implementation breaks tests from Phase N-1 or earlier

**Protocol:**
1. **Immediate:** Stop work, do NOT commit breaking changes
2. **Diagnosis:** Run `pytest tests/test_*.py -v` to identify failing tests
3. **Decision Tree:**
   ```
   ┌─ Regression Severity ──────────────────┐
   │ Minor (1-2 tests, isolated)?           │
   │   → Fix immediately, re-run guardrails │
   │                                        │
   │ Major (>2 tests, core functionality)?  │
   │   → Rollback changes (git reset)       │
   │   → Report to user                     │
   │   → Propose alternative approach       │
   └────────────────────────────────────────┘
   ```
4. **Recovery:** Re-implement with additional constraints to preserve backward compatibility
5. **Prevention:** Add regression test for detected failure mode

### Test Performance Budget Breach
**Trigger:** Test suite exceeds 30 second threshold

**Protocol:**
1. **Measure:** Run `pytest --durations=10` to identify slow tests
2. **Triage:**
   - **1-5 seconds over:** Optimize slow tests (reduce iterations, mock I/O)
   - **>5 seconds over:** Mark slow tests with `@pytest.mark.slow`, exclude from default run
3. **Report:** Include performance impact in commit message
4. **Escalate:** If budget cannot be met, propose test split or parallel execution

### Unresolvable Errors
**Trigger:** Code agent cannot fix error after 3 iteration attempts

**Protocol:**
1. **Document:** Capture exact error message, stack trace, attempted fixes
2. **Escalate to user:**
   ```
   [STATUS] BLOCKED

   [ERROR]
   <exact error message>
   <stack trace>

   [ATTEMPTED FIXES]
   1. <fix attempt 1> → <result>
   2. <fix attempt 2> → <result>
   3. <fix attempt 3> → <result>

   [REQUEST]
   Unable to resolve automatically. Requesting human guidance on:
   - <specific decision point 1>
   - <specific decision point 2>
   ```
3. **Wait:** Do not proceed until user provides guidance
4. **Alternative:** Propose minimal workaround to unblock (with caveats)

### Audit Failure (Cannot Reach Zero High/Medium Findings)
**Trigger:** Audit loop exceeds 5 iterations without resolution

**Protocol:**
1. **Document:** List all persistent findings with attempted remediation
2. **Escalate to user:**
   ```
   [AUDIT] BLOCKED - Cannot resolve findings after 5 iterations

   [PERSISTENT FINDINGS]
   - High #1: <description> → Attempted: <fix> → Result: <still failing>
   - Medium #2: <description> → Attempted: <fix> → Result: <still failing>

   [REQUEST]
   Requesting user decision:
   - Accept findings as-is (document in commit)
   - Change implementation approach
   - Defer feature to later phase
   ```
3. **Wait:** Do not commit until user provides direction

---

## Definition of Done (Per Task)

✅ **Code quality:**
- [ ] Formatted (`ruff format`)
- [ ] Linted (`ruff check .`)
- [ ] Type-checked (`mypy .`)
- [ ] Tested (`pytest`)

✅ **Documentation:**
- [ ] Docstrings for non-trivial public functions
- [ ] Inline comments for complex logic
- [ ] Config examples provided (if new config added)

✅ **Testing:**
- [ ] Unit tests for new functions/classes
- [ ] Integration test for new service interactions
- [ ] Golden test for deterministic outputs (if applicable)
- [ ] **Redis integration tests (REQUIRED for pub/sub, event bus, or Redis-dependent modules):**
  - [ ] Unit tests use `InMemoryBus` (no network I/O)
  - [ ] Integration test verifies Redis pub/sub round-trip
  - [ ] Test marked with `@pytest.mark.integration`
  - [ ] Skip guard implemented: `if os.getenv("REDIS_SKIP") == "1": pytest.skip()`
  - [ ] Docker Compose verified: `127.0.0.1` binding only (no `0.0.0.0`)
  - [ ] Integration test run during verification: `docker-compose -f docker-compose.test.yml up -d redis && pytest -v -m integration`

✅ **Audit** (Production Quality Gate)

**When Audit is Required:**
- ✅ **ALWAYS for:** New features (feat), bug fixes (fix), refactoring (refactor), performance (perf)
- ✅ **ALWAYS for:** New algorithms, execution logic, risk calculations, strategy implementations
- ⚠️ **OPTIONAL for:** Documentation only (docs), code style/formatting (style), dependency updates (chore)
- ❌ **SKIP for:** README updates, comment-only changes, typo fixes in non-code files

**Audit Process:**
- [ ] Audit sub-phase implementation per instructions in AUDIT.md
- [ ] Address all High and Medium severity findings:
  ```
  ┌─ Audit Loop ──────────────────────────┐
  │ 1. Make corrections for findings      │
  │ 2. Re-run affected checks:            │
  │    • Code changed? → make fmt lint    │
  │      type test                        │
  │    • Redis modules? → integration     │
  │      tests (docker-compose + pytest)  │
  │    • Docs only? → skip tests          │
  │    • Tests added? → make test         │
  │ 3. Re-audit implementation            │
  │ 4. Still have High/Medium findings?   │
  │    → Loop back to step 1              │
  │ 5. Zero High/Medium? → Exit loop      │
  └───────────────────────────────────────┘
  ```
- [ ] Present Low severity findings to user:
  - User approves applying? → make corrections → re-check → re-audit
  - User defers? → document in commit message
- [ ] Final verification: make fmt lint type test (all green)
- [ ] **Redis modules:** Integration tests green (docker-compose.test.yml + pytest -m integration)
- [ ] Audit must PASS before proceeding to Commit

✅ **Commit:** (Only After Audit Passes)
- [ ] Conventional commit message following format below
- [ ] **NO watermarks, footers, or attribution** (see prohibited patterns below)
- [ ] Include "Audit: PASS" in commit body if audit was performed
- [ ] Document any deferred Low severity findings in commit body
- [ ] Atomic change (single concern)
- [ ] All guardrails green

**Commit Message Format:**
```
✅ CORRECT format:
<type>(<scope>): <subject>

[Body describing implementation]

Audit: PASS (zero High/Medium findings)
[Optional: Deferred Low Findings: <brief description>]

[Optional footer: "Fixes #123" or "Breaking change: ..."]
```

**Prohibited commit message patterns:**
```
❌ NEVER include these footers:
🤖 Generated with [Claude Code](...)
Co-Authored-By: Claude <...>
Generated by AI
[Any other AI attribution or watermark]
```

---

## Communication Protocol (Agent ↔ Human)

### When to ask questions:
- Ambiguous requirements (e.g., "what should happen if X?")
- Missing dependencies or tools
- Breaking changes to existing APIs

### When NOT to ask:
- Standard patterns covered in this doc
- Common lint/type fixes (just fix them)
- Formatting preferences (follow `.editorconfig` + `ruff.toml`)

### Output format:
```
[STATUS] <green|red|blocked>

[CHANGES]
<unified diff or file blocks>

[VERIFICATION]
$ make fmt && make lint && make type && make test
<command output>

[NEXT STEPS] (optional)
<what to do next, if multi-step task>
```

---

## Appendix: Make Targets Reference

### Development & Quality
| Target | Description |
|--------|-------------|
| `make venv` | Create `./venv` virtual environment |
| `make install` | Install dev tools (ruff, mypy, pytest, pre-commit) |
| `make pre-commit` | Install git pre-commit hooks |
| `make fmt` | Format code with ruff |
| `make lint` | Lint code with ruff |
| `make type` | Type-check code with mypy |
| `make test` | Run full test suite (pytest) |
| `make next` | Show next planned phase/task from roadmap |

### Service Management
| Target | Description |
|--------|-------------|
| `make run-md SYMBOL=ATOM/USDT VENUE=binanceus` | Start market data ingest |
| `make run-strat` | Start strategy runner |
| `make run-broker` | Start broker service |
| `make run-risk` | Start risk engine |
| `make run-paper` | Start paper trader |

### Kill Switch
| Target | Description |
|--------|-------------|
| `make run-kill-trip` | Trip kill switch (file-based) |
| `make run-kill-clear` | Clear kill switch (file-based) |
| `make check-kill` | Check kill switch status |

---

## Appendix: Key Contracts Reference

### Event Types
```python
OrderIntent      # Strategy → Risk Engine
RiskDecision     # Risk Engine → Broker
OrderEvent       # Accepted order → Execution
FillEvent        # Execution → Position Manager
PositionSnapshot # Position state broadcast
```

### Broker Interface
```python
class IBroker(ABC):
    def place(req: BrokerOrderReq) -> BrokerOrderAck
    def cancel(exchange_order_id: str) -> bool
    def fetch_open_orders(symbol: str | None) -> list[BrokerOrderUpdate]
    def fetch_balances() -> list[BalanceSnapshot]
```

### Redis Topics
```yaml
md.trades.{symbol}   # Market data: trades
md.book.{symbol}     # Market data: order book
md.ticker.{symbol}   # Market data: ticker
strat.intent         # Strategy order intents
risk.decision        # Risk approval/denial
orders.accepted      # Accepted orders
fills.new            # Fill events
```

---

## Project Status

**Current Phase:** Phase 9 — Metrics & Telemetry
**Active Task:** Phase 9.0 — Metrics Contracts (next)
**Completed Phases:** 0-8 (Bootstrap through Execution Layer complete)
**See:** [ROADMAP.md](./ROADMAP.md) and `roadmap/phases/*.md` for complete phase history and specifications

---

## Document Changelog

**AGENTS.md version history (this file only):**

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial AGENTS.md operating guide for Phase 0 |
| 2.0 | 2025-10-04 | Enterprise-grade improvements: audit workflow integration, escalation & recovery protocols, logging policies, repository structure updates, Phase 3 documentation added |

**For project development history, see git log and ROADMAP.md**

---

**Last Updated:** 2025-10-04
**Maintained By:** Njord Trust
**License:** Proprietary
