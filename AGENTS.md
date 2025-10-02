# Njord Quant — Agent Operating Guide

## Mission Statement

Implement a **robust, research-driven algorithmic trading framework** for cryptocurrency markets in **16 incremental phases**. Each phase delivers small, reviewable diffs (≤150 LOC / ≤4 files) that maintain 100% green guardrails: formatted, linted, typed, and tested.

**Current Status:** Phase 3.8 — Strategy Plugin Framework
**Target:** Phase 16 — Production-ready autonomous trading system

## Documentation Hierarchy

This project maintains three levels of agent guidance:

1. **[AGENTS.md](./AGENTS.md)** (this file) — Strategic operating procedures, coding standards, and principles
2. **[ROADMAP.md](./ROADMAP.md)** — Tactical task-level instructions for each phase/sub-phase
3. **[CLAUDE.md](./CLAUDE.md)** — Claude Code entry point (references this file)

**For task execution:** Always consult ROADMAP.md for detailed behavioral specifications, acceptance criteria, and file locations. AGENTS.md defines *how* we build; ROADMAP.md defines *what* to build next.

---

## Top-Level SOPs (Strategic Operating Procedures)

### 1. Scope & Boundaries
- **Purpose:** Research → backtesting → paper trading → live trading pipeline
- **Exchange:** Binance.US (via CCXT Pro) with multi-exchange extensibility
- **Non-negotiables:**
  - Risk caps and kill-switch protections are **never bypassed**
  - **Never commit secrets** — `config/secrets.enc.yaml` stays encrypted
  - Production environment requires explicit flags (`env=live` + `NJORD_ENABLE_LIVE=1`)
  - Each phase **must not break prior phases** — earlier tests must remain green

### 2. Iteration Discipline
- **Atomic commits:** ≤150 lines of code, ≤4 files per commit
- **Green code mandate:** After every change, run:
  ```bash
  make fmt && make lint && make type && make test
  ```
- **Failure protocol:** If any check fails → **fix and rerun until all pass**
- **Output format:** Unified diff (patch) only — no prose explanations unless explicitly requested
- **Performance guardrail:** Test suite must complete in ≤30s; no long sleeps or unbounded loops

### 3. Coding Standards
| Standard | Specification |
|----------|---------------|
| **Python version** | 3.11 |
| **Type checking** | `mypy --strict` |
| **Formatting** | `ruff format` |
| **Linting** | `ruff check .` (rules: E, F, I, B, UP, SIM, RUF) |
| **Testing** | `pytest` (fast, deterministic, no network I/O) |
| **Import style** | `from core.contracts import X` (never top-level `contracts`) |

### 4. Repository Structure
```
njord_quant/
├── config/          # YAML configs (base.yaml, secrets.enc.yaml)
├── core/            # Framework primitives (bus, broker, contracts, logging)
├── apps/            # Service daemons (md_ingest, risk_engine, broker_binanceus, etc.)
├── strategies/      # Trading strategy plugins
├── risk/            # Risk rule modules
├── backtest/        # Replay engine and metrics
├── tests/           # Unit, integration, and golden tests
│   ├── unit/
│   ├── integration/
│   └── golden/
├── var/
│   ├── log/njord/   # NDJSON structured logs (via structlog)
│   └── state/       # Stateful watermarks and checkpoints
├── deploy/systemd/  # Service unit files
└── scripts/         # Operational scripts (kill switch, etc.)
```

### 5. Logging & Journaling
- **Format:** NDJSON via `structlog` → `var/log/njord/`
- **Journals:** Append-only NDJSON (rotation handled externally, not inline)
- **Topics:** Redis pub/sub for event streaming (`md.trades.{symbol}`, `risk.decisions`, etc.)

### 6. Commit Conventions
**Format:** Conventional Commits
```
<type>(<scope>): <subject>

Examples:
feat(core/logging): structured JSON logging helper + snapshot test
fix(broker): handle duplicate clientOrderId with idempotency
test(paper_trader): add position math partial close scenario
chore(mypy): exclude app __main__ entrypoints temporarily
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

### **Phase 3** — Live Broker (Binance.US) ✅
- 3.0–3.5: Adapter, reconnect, dry-run echo, $10 hard cap
- 3.6–3.7: Kill-switch enforcement (file + Redis)
- **3.8: Strategy Plugin Framework** ← **CURRENT PHASE**

### **Phase 3.8** — Strategy Plugin Framework ✅
**Status:** Complete
**Task:** Implement hot-swappable strategy system with context injection and order intent generation.

**Requirements:**
- Abstract base class `StrategyBase` with `on_event()` hook
- Strategy `Context` dataclass: current positions, recent prices, bus handle
- `OrderIntent` generation from strategy signals
- `StrategyRegistry` for discovery and instantiation
- `StrategyManager` for lifecycle (load, hot-reload, teardown)
- Config schema: `strategies.yaml` with per-strategy params
- Sample strategies: `trendline_break`, `rsi_tema_bb`
- Golden tests: deterministic signal generation
- Dry-run compliance: strategies never touch live broker directly

**Constraints:**
- No new dependencies beyond existing stack
- Strategies must be stateless or use provided `Context`
- All strategies must emit `OrderIntent` to risk engine (no direct broker calls)
- Keep each strategy ≤100 LOC
- Golden tests must remain ≤1k JSONL lines and live under `tests/golden/`

**Deliverables:**
1. `strategies/base.py` (ABC with `on_event()`)
2. `strategies/context.py` (injected state container)
3. `strategies/registry.py` (discovery + factory)
4. `strategies/manager.py` (lifecycle management)
5. `config/strategies.yaml` (config schema)
6. `strategies/samples/trendline_break.py`
7. `strategies/samples/rsi_tema_bb.py`
8. `tests/test_strategy_*.py` (golden signal tests)

---

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

### **Phase 8** — Execution Layer 📋
- Phase 8.0: Execution foundations (BusProto, BaseExecutor, sync/async adapters)
- Execution algorithms: TWAP, VWAP, Iceberg, POV
- Slippage models (linear, square-root)
- Smart order router with algorithm selection
- Execution performance metrics
- **Architecture:** All executors emit OrderIntent → Risk Engine → Broker (no bypass)

### **Phase 9** — Metrics & Telemetry
- Prometheus metrics exporter
- Grafana dashboard configs
- Strategy performance attribution

### **Phase 10** — Live Trade Controller
- Unified CLI (`njord-ctl start|stop|reload`)
- Config hot-reload
- Session journaling

### **Phase 11** — Monitoring & Alerts
- Alert bus (errors, kill-switch trips, PnL drawdowns)
- Slack/Email notification stubs (no secrets in repo)

### **Phase 12** — Compliance & Audit
- Append-only audit logs (immutable)
- Deterministic replay validation
- Order book reconstruction

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

**Note:** Detailed task specifications are maintained in [ROADMAP.md](./ROADMAP.md). Use this template for ad-hoc tasks not yet documented there.

Use this template when prompting agents for specific tasks:
...

```markdown
### Phase <N>.<M> — <Title>

**Task:**
<one-sentence summary>

**Requirements:**
- <bullet 1>
- <bullet 2>
- …

**Constraints:**
- No new **runtime** dependencies (Phases 0-6, 8-16)
  - **Exception:** Phase 7 (Research API) may add pandas, pyarrow, matplotlib, jupyter (optional group)
- No network I/O in tests
- Must stay deterministic
- Keep diffs minimal (≤150 LOC, ≤4 files)

**Output:**
Unified diff only. No prose.

**After patch, verify:**
```bash
make fmt && make lint && make type && make test
```

**Expected outcome:**
All checks pass (green). If red, iterate until green.
```

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

✅ **Commit:**
- [ ] Conventional commit message
- [ ] Atomic change (single concern)
- [ ] All guardrails green

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

| Target | Description |
|--------|-------------|
| `make venv` | Create `./venv` |
| `make install` | Install dev tools (ruff, mypy, pytest, pre-commit) |
| `make pre-commit` | Install git hooks |
| `make fmt` | Format code |
| `make lint` | Lint code |
| `make type` | Type-check code |
| `make test` | Run tests |
| `make run-md SYMBOL=ATOM/USDT VENUE=binanceus` | Start market data ingest |
| `make run-strat` | Start strategy runner |
| `make run-broker` | Start broker service |
| `make run-risk` | Start risk engine |
| `make run-paper` | Start paper trader |
| `make run-kill-trip` | Trip kill switch (file) |
| `make run-kill-clear` | Clear kill switch (file) |
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

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial bootstrap (Phase 0) |
| 2.0 | 2024-03 | Event bus + market data (Phase 1) |
| 3.0 | 2024-06 | Risk engine + paper OMS (Phase 2) |
| 3.8 | 2025-09 | Strategy plugin framework (Phase 3.8, in progress) |

---

**Last Updated:** 2025-09-30
**Maintained By:** Njord Trust
**License:** Proprietary
