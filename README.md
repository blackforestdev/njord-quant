# Njord Quant

Njord Quant is an enterprise-grade, local-first trading stack for cryptocurrency markets. The platform delivers a research-to-live pipeline with deterministic testing, strict risk controls, and modular services orchestrated through Redis pub/sub topics.

## Overview
- **Mission:** Provide a robust framework that takes strategies from research, through backtesting and paper trading, into live execution without compromising safety.
- **Exchange Coverage:** Binance.US via CCXT Pro, with pluggable adapters for future venues.
- **Runtime Model:** `systemd`-managed daemons; no Docker dependencies.
- **Data Guarantees:** Append-only NDJSON journaling, replayable event history, and deterministic goldens.

## Core Capabilities

### ✅ Implemented (Phases 0-9)

#### Trading Infrastructure (Phases 0-3)
- Market data ingestion with deduplication, journaling, and reconnect logic
- Strategy plugin framework with hot-swappable strategies emitting `OrderIntent` events
- Risk engine enforcing notional caps, loss limits, rate guards, and kill-switch controls
- Paper trading OMS and dry-run live broker adapter ensuring risk-first execution

#### Data & Analytics (Phases 4-7)
- Persistent OHLCV/tick storage with compression and replay hooks
- Deterministic backtesting engine with fill simulation, golden tests, and parameter sweeps
- Portfolio allocator with multi-strategy capital management, risk adjustment, and rebalancing
- Research API providing pandas/PyArrow access to journaled OHLCV, trades, fills, and positions
- Interactive HTML reporting with equity curves, allocations, and performance metrics

#### Execution Layer (Phase 8)
- TWAP/VWAP/Iceberg/POV execution algorithms with async/sync adapters
- Linear and square-root slippage models with market impact simulation
- Smart order router with algorithm selection logic based on order characteristics
- Execution simulator for backtest integration with deterministic fill generation
- Performance metrics tracker (implementation shortfall, benchmark comparisons, algorithm analysis)

#### Observability (Phase 9)
- Prometheus metrics exporter with HTTP /metrics endpoint
- Comprehensive metric contracts (MetricSnapshot, StrategyMetrics, SystemMetrics)
- Grafana dashboard configurations (system health, trading activity, strategy performance, execution quality)
- Metric aggregation service with downsampling and persistence
- Performance attribution engine (Brinson attribution, alpha/beta analysis)
- Real-time metrics dashboard with WebSocket/SSE streaming
- YAML-based alert rules engine with deduplication and multi-channel notifications
- Metrics retention management with automated cleanup and compression
- Complete telemetry documentation (metrics catalog, setup guide, operations runbook, API reference)

### 📋 Planned (Phases 10-16)

**Note:** Phases 10-16 are fully specified in the roadmap but not yet implemented. Implementation follows dependency order.

#### Observability & Compliance (Phases 10-12)
- **Phase 10 — Live Trade Controller:** Unified CLI (`njord-ctl`), process management, config hot-reload, session tracking
- **Phase 11 — Monitoring & Alerts:** Alert rules engine, multi-channel notifications, deduplication
- **Phase 12 — Compliance & Audit:** Immutable audit logging, deterministic replay validation, regulatory exports

#### Advanced Features (Phases 13-16)
- **Phase 13 — Advanced Strategy Toolkit:** ML-based signals, order flow imbalance, market regime detection, advanced indicators
- **Phase 14 — Simulation Harness:** Multi-day backtests, Monte Carlo simulation, scenario testing, walk-forward analysis
- **Phase 15 — Deployment Framework:** systemd templates, installation scripts, Ansible playbooks, health checks, backup/recovery
- **Phase 16 — Optimization Pass:** Performance profiling, memory optimization, code cleanup, API documentation, production validation

## System Architecture

### Implemented Components

- **core/**: Shared primitives (Pydantic config loader, structured logging, Redis bus wrapper, contracts, kill-switch helpers, NDJSON journals)
- **apps/**: Long-running service daemons deployed under `systemd`:
  - `md_ingest` — Market data ingestion with CCXT Pro
  - `risk_engine` — Risk policy enforcement and kill-switch integration
  - `paper_trader` — Simulated order management system
  - `broker_binanceus` — Live Binance.US adapter with dry-run safeguards
  - `portfolio_manager` — Multi-strategy capital allocation and rebalancing
  - `strategy_runner` — Strategy plugin framework executor
  - `ohlcv_aggregator` — Real-time OHLCV candle aggregation
  - `replay_engine` — Event replay for backtesting and simulation
- **strategies/**: Strategy plugin framework with registry, manager, sample strategies (trendline break, RSI+TEMA+BB), and golden tests
- **risk/**: Risk policy modules (notional caps, loss limits, rate guards) applied by risk engine
- **backtest/**: Deterministic replay engine, fill simulation, analytics tooling, reporting assets
- **portfolio/**: Multi-strategy allocator components (contracts, allocation logic, rebalancer, backtests, reporting)
- **research/**: Data reader, aggregation stack, validation tools, export utilities, research CLI
- **execution/**: Execution algorithms (TWAP, VWAP, Iceberg, POV), slippage models, smart order router, performance tracker
- **telemetry/**: Prometheus exporter, metric contracts, aggregation service, performance attribution, alert manager, retention policies
- **apps/metrics_dashboard/**: Real-time metrics dashboard with SSE streaming and interactive UI
- **docs/telemetry/**: Complete documentation (metrics catalog, Grafana setup guide, operations runbook, API reference)
- **tests/**: Unit, integration, and golden test suites (80+ test files) ensuring strict guardrails
- **var/**: Structured logs and runtime state (append-only NDJSON)

### Planned Components (Phases 10-16)

- **controller/** (Phase 10): Process manager, config hot-reload, session tracking, health checks, log aggregation
- **alerts/** (Phase 11): Alert rules engine, notification channels (log/Redis/webhook/email/Slack), alert CLI
- **compliance/** (Phase 12): Audit logger, replay engine, order book reconstruction, regulatory reporting

### Event Flow

1. `apps/md_ingest` streams trades/books via CCXT Pro, deduplicates events, and publishes to Redis topics (`md.trades.*`, `md.book.*`) while journaling to `var/log/njord/`
2. Strategies subscribe to the bus, build signals using injected context (positions, prices, utilities), and emit `OrderIntent` events
3. The risk engine validates intents against kill switches, caps, and policy modules, publishing `risk.decisions` for approved orders
4. Paper trader or live broker services act on decisions, generate fills and position snapshots, and broadcast results back to the bus
5. Portfolio manager tracks fills, executes rebalancing logic, and publishes portfolio snapshots

## Documentation Map

- **[ROADMAP.md](./ROADMAP.md)**: Phase-by-phase implementation index (Phases 0-16, hierarchical structure)
- **[roadmap/phases/*.md](./roadmap/phases/)**: Detailed phase specifications with acceptance criteria
- **[AGENTS.md](./AGENTS.md)**: Strategic operating procedures, coding standards, and non-negotiable guardrails
- **[CLAUDE.md](./CLAUDE.md)**: Claude Code entry point referencing AGENTS.md
- **[docs/](./docs)**: Supplemental design notes and decision records (as available)

## Current Phase

**Phase 10 — Live Trade Controller** 📋 *(Planned, Not Implemented)*

Next steps:
- Controller contracts (ServiceStatus, SessionSnapshot, ControlCommand)
- Service registry for tracking all njord services
- Process manager with systemd integration and service lifecycle control
- Config hot-reload with file watchers, validation, and safe reload
- Session manager with session journaling and metadata persistence
- Log aggregation with centralized logging, filtering, and export
- CLI framework (`njord-ctl` commands for service control)
- Service health checks with endpoint monitoring and dependency checks
- Controller service integration and orchestration

See **[roadmap/phases/phase-10-controller.md](./roadmap/phases/phase-10-controller.md)** for detailed specifications.

## Project Structure

```text
njord_quant/
├── apps/               # Service daemons (implemented)
│   ├── md_ingest/      # Market data ingestion (CCXT Pro)
│   ├── risk_engine/    # Risk policy enforcement
│   ├── paper_trader/   # Simulated OMS
│   ├── broker_binanceus/ # Live Binance.US adapter
│   ├── portfolio_manager/ # Multi-strategy allocator
│   ├── strategy_runner/ # Strategy framework executor
│   ├── ohlcv_aggregator/ # Real-time candle aggregation
│   └── replay_engine/  # Event replay engine
├── backtest/           # Backtesting engine and analytics
├── config/             # Environment configuration and encrypted secrets
├── core/               # Shared primitives (config, logging, bus, contracts, journals)
├── data/               # Data storage (OHLCV, trades, fills)
├── deploy/             # Deployment scripts and systemd templates
├── docs/               # Design notes and decision records
├── execution/          # Execution algorithms (TWAP, VWAP, Iceberg, POV), router, performance
├── experiments/        # Research experiments and notebooks
├── portfolio/          # Portfolio allocator components
├── research/           # Data reader, aggregation, export utilities
├── risk/               # Risk policy modules
├── roadmap/            # Phase specifications (hierarchical)
├── scripts/            # Operational scripts (kill-switch, validation)
├── strategies/         # Strategy plugin framework and samples
├── tests/              # Unit, integration, and golden test suites (80+ files)
└── var/                # Structured logs and runtime state (NDJSON)
```

## Getting Started

1. **Create virtual environment:**
   ```bash
   python3 -m venv venv && source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   make install
   ```

3. **Configure environment:**
   - Update `config/base.yaml` (Redis, exchange, risk limits)
   - Update `config/strategies.yaml` (strategy registry)
   - Update `config/portfolio.yaml` (capital allocation)
   - Keep secrets encrypted in `config/secrets.enc.yaml` (SOPS)

4. **Run services locally:**
   ```bash
   make run-md        # Market data ingestion
   make run-risk      # Risk engine
   make run-paper     # Paper trader
   make run-strat     # Strategy runner
   ```

5. **Inspect logs:**
   - Check `var/log/njord/` for structured NDJSON logs
   - Review journal outputs to validate event flow

6. **Run tests:**
   ```bash
   make fmt lint type test  # All guardrails must be green
   ```

## Development Workflow & Guardrails

- **Python 3.11** with `ruff` (format/lint), `mypy --strict`, and `pytest`
- **Guardrails must remain green:**
  ```bash
  make fmt && make lint && make type && make test
  ```
- **Commits:**
  - Follow Conventional Commit format (`feat:`, `fix:`, `docs:`, `refactor:`, etc.)
  - Remain ≤150 LOC across ≤4 files per commit
- **Tests:**
  - Must be deterministic (no network I/O, no long sleeps)
  - Use fixed seeds or injected clocks when needed
  - Golden tests for strategy signal validation
- **Security:**
  - Never bypass kill-switch checks
  - Never commit decrypted secrets
  - Always use SOPS encryption for `config/secrets.enc.yaml`

## Implemented Services

| Service | Description | Path |
|---------|-------------|------|
| **md_ingest** | CCXT Pro market data daemon with deduplication, backoff, and journaling | `apps/md_ingest/` |
| **risk_engine** | Validates `OrderIntent` events against policy modules and kill-switch state | `apps/risk_engine/` |
| **paper_trader** | Simulated fills, position tracking, and PnL calculations | `apps/paper_trader/` |
| **broker_binanceus** | Live adapter enforcing dry-run defaults, notional caps, and kill-switch compliance | `apps/broker_binanceus/` |
| **portfolio_manager** | Coordinates strategy fills, rebalancing, and publishes portfolio snapshots | `apps/portfolio_manager/` |
| **strategy_runner** | Loads and executes strategies from strategy registry | `apps/strategy_runner/` |
| **ohlcv_aggregator** | Real-time OHLCV candle aggregation and publishing | `apps/ohlcv_aggregator/` |
| **replay_engine** | Event replay for backtesting and deterministic simulation | `apps/replay_engine/` |

### Implemented Services (Phase 9)

- **metrics_dashboard** (Phase 9): Real-time metrics dashboard with SSE streaming on `http://localhost:8080`

### Planned Services (Phases 10-12)

- **Phase 10:** Process manager (`njord-ctl` CLI), config hot-reload, session tracking, health checks
- **Phase 11:** Alert service with multi-channel notifications (log/Redis/webhook/email/Slack)
- **Phase 12:** Audit service with immutable logging, replay validation, and regulatory exports

## Configuration Files

### Implemented Configuration

| File | Purpose |
|------|---------|
| `config/base.yaml` | Core settings (environment, Redis endpoints, logging, risk limits) |
| `config/strategies.yaml` | Strategy registry and parameterization |
| `config/portfolio.yaml` | Portfolio allocation and rebalancing rules |
| `config/secrets.enc.yaml` | SOPS-encrypted secrets (API keys, credentials) |

### Planned Configuration (Phases 10-12)

- `config/controller.yaml` — Service registry and process management settings (Phase 10)
- `config/alerts.yaml` — Alert rules and notification channels (Phase 11)
- `config/compliance.yaml` — Audit/replay settings, regulatory export templates (Phase 12)

### Configuration Guidelines

- **Live trading** requires explicit flags: `app.env=live` AND `NJORD_ENABLE_LIVE=1`
- **Secrets:** Use `${ENV_VAR_NAME}` syntax for environment variable references
- **SOPS encryption:** Always encrypt secrets at rest, never commit decrypted values
- **Feature gates:** Metrics/alerts/audit gated by env vars (disabled in tests by default)

## Logging & Observability

### Implemented

- **Structured Logging:** `structlog` writes NDJSON entries to `var/log/njord/`
  - Application logs, event journals, error traces
  - Append-only, replayable, machine-parseable
- **Event Journals:** Market data, order intents, risk decisions, fills, positions
- **Kill-Switch Monitoring:**
  - File-based: `/tmp/njord_killswitch` presence trips all services
  - Redis-based: `njord:killswitch` key trips all services
- **Operational Scripts:** Located in `scripts/` for kill-switch control, status checks

### Implemented (Phase 9)

- **Phase 9 — Metrics & Telemetry:**
  - Prometheus exporter on `http://localhost:9091/metrics`
  - Comprehensive metric contracts and registry
  - Metric aggregation service with downsampling and persistence
  - Performance attribution engine (Brinson, alpha/beta)
  - Real-time metrics dashboard on `http://localhost:8080` with SSE streaming
  - YAML-based alert rules engine with deduplication
  - Metrics retention management with automated cleanup and compression
  - Complete telemetry documentation

### Planned (Phases 10-12)

- **Phase 10 — Process Control:**
  - `njord-ctl` CLI for start/stop/restart/reload/status/logs/session management
  - Config hot-reload with validation
  - Session tracking and health checks
- **Phase 11 — Monitoring & Alerts:**
  - Enhanced alert rules engine, multi-channel notifications
  - Publishes to `var/log/njord/alerts.ndjson` and configured channels
- **Phase 12 — Compliance & Audit:**
  - Immutable audit logging, deterministic replay validation
  - Regulatory export utilities, order book reconstruction

## Security & Best Practices

### Secrets Management

- **Environment Variables:** All secrets loaded from env vars
- **Config References:** Use `${ENV_VAR_NAME}` syntax in YAML configs
- **SOPS Encryption:** `config/secrets.enc.yaml` encrypted at rest (never commit decrypted)
- **No Hardcoded Secrets:** Repository contains zero plaintext credentials

### Feature Gating

- **Live Trading:** Requires `app.env=live` in config AND `NJORD_ENABLE_LIVE=1` env var
- **Metrics Emission:** Gated by `NJORD_ENABLE_METRICS=1` (disabled in tests by default)
- **Alert Notifications:** Gated by `NJORD_ENABLE_ALERTS=1` (disabled in tests by default)
- **Audit Logging:** Gated by `NJORD_ENABLE_AUDIT=1` (disabled in tests by default)

### Kill-Switch Enforcement

- **File-Based:** `/tmp/njord_killswitch` (or configurable path) presence trips all services
- **Redis-Based:** `njord:killswitch` key trips all services
- **Process Manager (Planned):** Checks kill-switch before starting live services (refuses if tripped)
- **Alert Integration (Planned):** Critical alerts fire when kill-switch triggered

### Network Security (Implemented Phase 9 / Planned Phases 10-12)

*The following bindings apply to telemetry and planned services (Phases 9-12):*

- **Metrics Exporter (Phase 9):** Binds to `127.0.0.1:9091` by default (Prometheus scraper must be local or tunneled)
- **Metrics Dashboard (Phase 9):** Binds to `127.0.0.1:8080` by default (web access via SSH tunnel or local browser)
- **Controller API (Phase 10):** Binds to `127.0.0.1:9092` by default (njord-ctl commands local only)
- **Alert Service (Phase 11):** Health check on `127.0.0.1:9093` by default
- **Production Access:** Explicitly set `bind_host` parameter to expose on network interfaces

## Make Targets

### Development

```bash
make help          # Show all available targets
make install       # Create venv and install dependencies
make fmt           # Format code with ruff
make lint          # Lint code with ruff
make type          # Type-check with mypy --strict
make test          # Run pytest test suite
```

### Roadmap Navigation

```bash
make roadmap       # View phase index
make status        # Show current phase status
make next          # Show next planned task
make phase-current # Open current phase file
make phase NUM=8   # Open specific phase file
```

### Polish Backlog Workflow

Pending polish items are tracked alongside the roadmap so they do not get lost:

1. When a sub-phase closes, capture any optional improvements in a short "Polish / Follow-ups" list inside that phase file (e.g. `roadmap/phases/phase-09-telemetry.md`).
2. Mirror those bullets in the global backlog at the end of `ROADMAP_REFACTOR_PLAN.md`.
3. When the item is addressed (either by a later sub-phase or during Phase 16), remove it from both lists so the backlog stays current.

This keeps polish tasks visible next to their context while providing a single checklist for the Phase 16 optimization sweep.

### Service Execution

```bash
make run-md        # Run market data ingestion
make run-risk      # Run risk engine
make run-paper     # Run paper trader
make run-strat     # Run strategy runner
make run-broker    # Run live broker (dry-run by default)
```

### Kill-Switch Control

```bash
make run-kill-trip  # Trip kill-switch
make run-kill-clear # Clear kill-switch
make check-kill     # Check kill-switch status
```

### Logs & Journals

```bash
make journal       # Tail journal logs
```

## Roadmap Snapshot

### ✅ Implemented (Phases 0-9)

- **Phase 0 — Bootstrap & Guardrails:** Tooling, config loader, structured logging, NDJSON journal
- **Phase 1 — Event Bus & Market Data:** Redis bus, contracts, market data ingest daemon
- **Phase 2 — Risk Engine & Paper OMS:** Risk policies, paper trader, kill-switch integrations
- **Phase 3 — Strategy Plugin Framework:** Live broker adapter, strategy registry/manager, sample strategies
- **Phase 4 — Market Data Storage:** Persistent OHLCV/tick storage, compression, replay hooks
- **Phase 5 — Backtester:** Contracts, engine core, fill simulation, equity curve, metrics, CLI, golden tests, parameter sweeps, reporting
- **Phase 6 — Portfolio Allocator:** Multi-strategy capital allocation, risk adjustment, portfolio backtesting, reporting
- **Phase 7 — Research API:** Data reader, aggregation stack, research CLI, documentation
- **Phase 8 — Execution Layer:** TWAP/VWAP/Iceberg/POV algorithms, slippage models, smart order router, execution simulator, performance metrics
- **Phase 9 — Metrics & Telemetry:** Prometheus exporter, metric contracts, aggregation service, performance attribution, real-time dashboard, alert system, retention management, complete documentation

### 📋 Planned (Phases 10-16)

**Note:** Fully specified in roadmap, not yet implemented. Implementation follows dependency order: 10 → 11 → 12 → 13 → 14 → 15 → 16.

- **Phase 10 — Live Trade Controller:** Unified CLI (njord-ctl), process management, config hot-reload, session tracking
- **Phase 11 — Monitoring & Alerts:** Alert rules engine, multi-channel notifications, deduplication
- **Phase 12 — Compliance & Audit:** Immutable audit logging, deterministic replay validation, regulatory exports
- **Phase 13 — Advanced Strategy Toolkit:** ML signals, order flow imbalance, market regime detection, advanced indicators
- **Phase 14 — Simulation Harness:** Multi-day backtests, Monte Carlo simulation, scenario testing, walk-forward analysis
- **Phase 15 — Deployment Framework:** systemd templates, installation scripts, Ansible playbooks, health checks, backup/recovery
- **Phase 16 — Optimization Pass:** Performance profiling, memory optimization, code cleanup, API documentation, production validation

See **[ROADMAP.md](./ROADMAP.md)** for complete phase index and navigation to detailed specifications.

## Support & Licensing

- **Maintained by:** Njord Trust LLC
- **License:** Proprietary — Consult organizational policies for usage and distribution rights
- **Issues & Contributions:** Contact internal development team for guidance

---

**Last Updated:** 2025-10-07
**Current Phase:** 10 (Live Trade Controller) — Planned, not implemented
**Roadmap Status:** Phases 0-9 complete ✅ | Phases 10-16 specified 📋
