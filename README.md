# Njord Quant

Njord Quant is an enterprise-grade, local-first trading stack for cryptocurrency markets. The platform delivers a research-to-live pipeline with deterministic testing, strict risk controls, and modular services orchestrated through Redis pub/sub topics.

## Overview
- **Mission:** Provide a robust framework that takes strategies from research, through backtesting and paper trading, into live execution without compromising safety.
- **Exchange Coverage:** Binance.US via CCXT Pro, with pluggable adapters for future venues.
- **Runtime Model:** `systemd`-managed daemons; no Docker dependencies.
- **Data Guarantees:** Append-only NDJSON journaling, replayable event history, and deterministic goldens.

## Core Capabilities
- Market data ingestion with deduplication, journaling, and reconnect logic.
- Strategy plugin framework with hot-swappable strategies that emit `OrderIntent` events routed through the risk engine.
- Risk engine enforcing notional caps, loss limits, rate guards, and kill-switch controls.
- Paper trading OMS and dry-run live broker adapter to ensure risk-first execution.
- Deterministic backtesting engine with replay, fill simulation, golden tests, and report generation.
- Portfolio allocator (Phase 6) introducing multi-strategy capital management, rebalancing, and portfolio reporting.
- Risk-adjusted allocator (Phase 6.7) that modulates capital based on strategy performance metrics.
- Portfolio backtest engine (Phase 6.8) aggregating strategy runs into portfolio-level equity and metrics.
- Research data reader (Phase 7.1) providing pandas/PyArrow access to journaled OHLCV, trades, fills, and positions.
- Portfolio report generator (Phase 6.9) producing interactive HTML summaries with allocations and rebalances.

## System Architecture
- **core/**: Shared primitives such as the Pydantic config loader, structured logging, Redis bus wrapper, contracts, kill switch helpers, and NDJSON journals.
- **apps/**: Long-running services (`md_ingest`, `risk_engine`, `paper_trader`, `broker_binanceus`) deployed under `systemd`.
- **strategies/**: Strategy plugin framework with registry/manager, sample strategies, and golden tests for deterministic signal generation.
- **risk/**: Risk policy modules applied by the risk engine.
- **backtest/**: Deterministic replay engine, fill simulation, analytics tooling, and reporting assets.
- **portfolio/**: Multi-strategy allocator components (contracts, allocation logic, rebalancer, backtests, reporting).
- **tests/**: Unit, integration, and golden suites ensuring strict guardrails.

### Event Flow
1. `apps/md_ingest` streams trades/books via CCXT Pro, deduplicates events, and publishes to Redis topics (`md.trades.*`, `md.book.*`) while journaling to `var/log/njord/`.
2. Strategies subscribe to the bus, build signals using injected context (positions, prices, utilities), and emit `OrderIntent` events.
3. The risk engine validates intents against kill switches, caps, and policy modules, publishing `risk.decisions` for approved orders.
4. Paper trader or live broker services act on decisions, generate fills and position snapshots, and broadcast results back to the bus.

## Documentation Map
- [AGENTS.md](./AGENTS.md): Strategic SOPs, coding standards, and non-negotiable guardrails.
- [ROADMAP.md](./ROADMAP.md): Phase-by-phase implementation tasks and acceptance criteria (current focus: Phase 6).
- [CLAUDE.md](./CLAUDE.md): Claude Code entry point referencing AGENTS.md.
- [docs/](./docs): Supplemental design notes and decision records (as available).

## Current Phase
**Phase 7 — Research API**
- Kickstarts researcher tooling with portfolio-aware data access (pandas/PyArrow), backtest result loaders, and notebook-friendly helpers.
- Builds on the completed portfolio allocator (Phase 6) to surface strategy and portfolio metrics for offline analysis.
See [ROADMAP.md#phase-7-—-research-api](./ROADMAP.md#phase-7-—-research-api) for the upcoming task breakdown and acceptance criteria.

## Project Structure
```text
njord_quant/
├── apps/               # Service daemons (md_ingest, risk_engine, paper_trader, broker_binanceus)
├── backtest/           # Backtesting engine components and analytics tooling
├── config/             # Environment configuration and encrypted secrets
├── core/               # Shared primitives (config, logging, bus, contracts, journals, kill switch)
├── risk/               # Risk rule modules
├── strategies/         # Strategy plugin framework and samples
├── portfolio/          # Portfolio allocator, risk adjustment, reporting, and manager integration
├── research/           # Data reader, aggregation, and research tooling (Phase 7)
├── tests/              # Unit, integration, and golden suites
└── var/                # Structured logs and runtime state (append-only NDJSON)
```

## Getting Started
1. Create a virtual environment: `python3 -m venv venv && source venv/bin/activate`
2. Install dependencies and tooling: `make install`
3. Configure environment files: update `config/base.yaml` and `config/strategies.yaml`; keep secrets encrypted in `config/secrets.enc.yaml`
4. Run services locally using the provided make targets (`make run-md`, `make run-risk`, `make run-paper`, `make run-strat`)
5. Inspect logs under `var/log/njord/` and journal outputs to validate event flow

## Development Workflow & Guardrails
- Python 3.11 with `ruff` (format/lint), `mypy --strict`, and `pytest`; guardrails must remain green.
- Run `make fmt && make lint && make type && make test` before submitting changes.
- Commits follow Conventional Commit format and remain ≤150 LOC across ≤4 files.
- Tests must be deterministic: avoid network I/O and long sleeps; use fixed seeds or injected clocks when needed.
- Never bypass kill-switch checks or commit decrypted secrets.

## Services & Workloads
- `apps/md_ingest`: CCXT Pro market data daemon with deduplication, backoff, and journaling.
- `apps/risk_engine`: Validates `OrderIntent` events against policy modules and kill-switch state.
- `apps/paper_trader`: Simulated fills, position tracking, and PnL calculations for dry-run environments.
- `apps/broker_binanceus`: Live adapter enforcing dry-run defaults, notional caps, and kill-switch compliance.
- `apps/portfolio_manager`: Coordinates strategy fills, rebalancing, and publishes portfolio snapshots.

## Configuration & Secrets
- `config/base.yaml`: Core application settings (environment, Redis endpoints, logging directories).
- `config/strategies.yaml`: Strategy registry and parameterization for the plugin framework.
- `config/portfolio.yaml`: Example portfolio configuration consumed by the portfolio manager service.
- `config/secrets.enc.yaml`: SOPS-encrypted secrets; never commit decrypted values.
- Live trading requires explicit flags: `app.env=live` and `NJORD_ENABLE_LIVE=1`.

## Logging & Observability
- Structured logging via `structlog` writes NDJSON entries to `var/log/njord/`.
- Journals capture market data, intents, and fills for replay and audit.
- Operational scripts (kill switch, status checks) live in `scripts/`; systemd units reside in `deploy/systemd/`.

## Roadmap Snapshot
- **Phase 0 — Bootstrap & Guardrails:** Tooling, config loader, structured logging, NDJSON journal ✅
- **Phase 1 — Event Bus & Market Data:** Redis bus, contracts, market data ingest daemon ✅
- **Phase 2 — Risk Engine & Paper OMS:** Risk policies, paper trader, kill-switch integrations ✅
- **Phase 3 — Live Broker:** Binance.US adapter with dry-run safeguards and kill-switch enforcement ✅
- **Phase 4 — Market Data Storage:** Persistent OHLCV/tick storage, compression, and replay hooks ✅
- **Phase 5 — Backtester:** Contracts, engine core, fill simulation, equity curve, metrics, CLI, golden tests, parameter sweeps, and reporting ✅
- **Phase 6 — Portfolio Allocator:** Multi-strategy capital allocation, risk adjustment, portfolio backtesting, and reporting ✅
- **Phase 7–16:** Research APIs, execution enhancements, telemetry, compliance, deployment, and optimization initiatives 📋

## Support & Licensing
- Maintained by **Njord Trust**.
- Proprietary license; consult organizational policies for usage and distribution rights.
