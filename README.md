# Njord Quant

Njord Quant is an enterprise-grade, local-first trading stack for cryptocurrency markets. The platform delivers a research-to-live pipeline with deterministic testing, strict risk controls, and modular services orchestrated through Redis pub/sub topics.

## Overview
- **Mission:** Provide a robust framework that takes strategies from research, through backtesting and paper trading, into live execution without compromising safety.
- **Exchange Coverage:** Binance.US via CCXT Pro, with pluggable adapters for future venues.
- **Runtime Model:** `systemd`-managed daemons; no Docker dependencies.
- **Data Guarantees:** Append-only NDJSON journaling, replayable event history, and deterministic goldens.

## Core Capabilities

### Trading Infrastructure (Phases 0-3) ✅
- Market data ingestion with deduplication, journaling, and reconnect logic
- Strategy plugin framework with hot-swappable strategies emitting `OrderIntent` events
- Risk engine enforcing notional caps, loss limits, rate guards, and kill-switch controls
- Paper trading OMS and dry-run live broker adapter ensuring risk-first execution

### Data & Analytics (Phases 4-7) ✅
- Persistent OHLCV/tick storage with compression and replay hooks
- Deterministic backtesting engine with fill simulation, golden tests, and parameter sweeps
- Portfolio allocator with multi-strategy capital management, risk adjustment, and rebalancing
- Research API providing pandas/PyArrow access to journaled OHLCV, trades, fills, and positions
- Interactive HTML reporting with equity curves, allocations, and performance metrics

### Execution, Observability & Compliance (Phases 8-12) 📋
- **Execution Layer (Phase 8):** TWAP/VWAP/Iceberg/POV algorithms, slippage models, smart order routing
- **Metrics & Telemetry (Phase 9):** Prometheus exporter, Grafana dashboards, performance attribution, real-time metrics (gated by `NJORD_ENABLE_METRICS`)
- **Live Trade Controller (Phase 10):** Unified CLI (`njord-ctl`), process management, config hot-reload, session tracking, log aggregation
- **Monitoring & Alerts (Phase 11):** Alert rules engine, multi-channel notifications (log/Redis/webhook/email/Slack stubs), deduplication (gated by `NJORD_ENABLE_ALERTS`)
- **Compliance & Audit (Phase 12):** Immutable audit logging, deterministic replay validation, order book reconstruction, regulatory exports, audit CLI/service (gated by `NJORD_ENABLE_AUDIT`)

## System Architecture
- **core/**: Shared primitives such as the Pydantic config loader, structured logging, Redis bus wrapper, contracts, kill switch helpers, and NDJSON journals.
- **apps/**: Long-running services (`md_ingest`, `risk_engine`, `paper_trader`, `broker_binanceus`, `portfolio_manager`, `alert_service`) deployed under `systemd`.
- **strategies/**: Strategy plugin framework with registry/manager, sample strategies, and golden tests for deterministic signal generation.
- **risk/**: Risk policy modules applied by the risk engine.
- **backtest/**: Deterministic replay engine, fill simulation, analytics tooling, and reporting assets.
- **portfolio/**: Multi-strategy allocator components (contracts, allocation logic, rebalancer, backtests, reporting).
- **execution/**: Execution algorithms (TWAP, VWAP, Iceberg, POV), slippage models, smart order router.
- **research/**: Data reader, aggregation stack, validation tools, export utilities, and research CLI.
- **telemetry/**: Prometheus exporter, metric aggregation, performance attribution, real-time dashboard.
- **controller/**: Process manager, config hot-reload, session tracking, health checks, log aggregation.
- **alerts/**: Alert rules engine, notification channels (log/Redis/webhook/email/Slack), alert CLI.
- **tests/**: Unit, integration, and golden suites ensuring strict guardrails.

### Event Flow
1. `apps/md_ingest` streams trades/books via CCXT Pro, deduplicates events, and publishes to Redis topics (`md.trades.*`, `md.book.*`) while journaling to `var/log/njord/`.
2. Strategies subscribe to the bus, build signals using injected context (positions, prices, utilities), and emit `OrderIntent` events.
3. The risk engine validates intents against kill switches, caps, and policy modules, publishing `risk.decisions` for approved orders.
4. Paper trader or live broker services act on decisions, generate fills and position snapshots, and broadcast results back to the bus.

## Documentation Map
- [AGENTS.md](./AGENTS.md): Strategic SOPs, coding standards, and non-negotiable guardrails.
- [ROADMAP.md](./ROADMAP.md): Phase-by-phase implementation tasks and acceptance criteria (Phases 0-12 specified).
- [CLAUDE.md](./CLAUDE.md): Claude Code entry point referencing AGENTS.md.
- [docs/](./docs): Supplemental design notes and decision records (as available).

## Current Phase
**Phase 8 — Execution Layer** 📋
- Execution layer foundations (BusProto, BaseExecutor, sync/async adapters)
- TWAP/VWAP/Iceberg/POV execution algorithms
- Slippage models (linear, square-root market impact)
- Smart order router with algorithm selection logic
- Execution simulator for backtest integration
- Execution performance metrics (implementation shortfall, slippage tracking)

See [ROADMAP.md](./ROADMAP.md) for detailed implementation specifications. **Note:** Phases 8-13 are fully specified but not yet implemented. Implementation follows dependency order: 8 → 9 → 10 → 11 → 12 → 13.

## Project Structure
```text
njord_quant/
├── apps/               # Service daemons (md_ingest, risk_engine, paper_trader, broker_binanceus,
│                       #                  portfolio_manager, alert_service, metrics_dashboard)
├── backtest/           # Backtesting engine components and analytics tooling
├── config/             # Environment configuration and encrypted secrets
├── core/               # Shared primitives (config, logging, bus, contracts, journals, kill switch)
├── risk/               # Risk rule modules
├── strategies/         # Strategy plugin framework and samples
├── portfolio/          # Portfolio allocator, risk adjustment, reporting, and manager integration
├── execution/          # Execution algorithms (TWAP, VWAP, Iceberg, POV), slippage models, router
├── research/           # Data reader, aggregation, validation, export utilities, research CLI
├── telemetry/          # Prometheus exporter, metric aggregation, performance attribution
├── controller/         # Process manager, config hot-reload, session tracking, health checks
├── alerts/             # Alert rules engine, notification channels, alert CLI
├── compliance/         # Audit logger, replay engine, order book reconstruction, reporting
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
- `apps/metric_aggregator`: Aggregates metrics, downsamples data, publishes to Prometheus exporter.
- `apps/metrics_dashboard`: Real-time web dashboard with auto-refresh metrics (WebSocket/SSE).
- `apps/alert_service`: Evaluates alert rules, routes notifications to configured channels (gated by `NJORD_ENABLE_ALERTS`).
- `apps/audit_service`: Real-time immutable audit logging, query & integrity verification APIs (gated by `NJORD_ENABLE_AUDIT`).
- `controller/`: Unified CLI (`njord-ctl`) for process management, config reload, session tracking.

## Configuration & Secrets
- `config/base.yaml`: Core application settings (environment, Redis endpoints, logging directories).
- `config/strategies.yaml`: Strategy registry and parameterization for the plugin framework.
- `config/portfolio.yaml`: Portfolio configuration consumed by the portfolio manager service.
- `config/alerts.yaml`: Alert rules and notification channel configuration.
- `config/compliance.yaml`: Audit/replay settings, regulatory export templates.
- `config/secrets.enc.yaml`: SOPS-encrypted secrets; never commit decrypted values.
- Live trading requires explicit flags: `app.env=live` and `NJORD_ENABLE_LIVE=1`.
- Metrics/alerts/audit gated by env vars: `NJORD_ENABLE_METRICS=1`, `NJORD_ENABLE_ALERTS=1`, `NJORD_ENABLE_AUDIT=1`.

## Logging & Observability
- **Structured Logging:** `structlog` writes NDJSON entries to `var/log/njord/` (app logs, journals, alerts).
- **Metrics:** Prometheus exporter on `http://localhost:9090/metrics` (localhost-only by default).
- **Dashboards:** Grafana configs for system health, trading activity, strategy performance, execution quality.
- **Real-time Dashboard:** Metrics dashboard on `http://localhost:8080` with 1-second auto-refresh.
- **Alerts:** Alert service evaluates rules, publishes to `var/log/njord/alerts.ndjson` and configured channels.
- **Process Control:** `njord-ctl` CLI for start/stop/restart/reload/status/logs/session management.
- Operational scripts (kill switch, status checks) live in `scripts/`; systemd units reside in `deploy/systemd/`.

## Security & Best Practices

### Localhost-Only Binding (Defense in Depth)
- **Metrics Exporter:** Binds to `127.0.0.1:9090` by default (Prometheus scraper must be local or tunneled)
- **Metrics Dashboard:** Binds to `127.0.0.1:8080` by default (web access via SSH tunnel or local browser)
- **Controller API:** Binds to `127.0.0.1:9091` by default (njord-ctl commands local only)
- **Alert Service:** Health check on `127.0.0.1:9092` by default
- **Production Access:** Explicitly set `bind_host` parameter to expose on network interfaces

### Secrets Management
- **Environment Variables:** All secrets loaded from env vars (webhook URLs, SMTP credentials, API tokens)
- **Config References:** Use `${ENV_VAR_NAME}` syntax in YAML configs (e.g., `${NJORD_ALERT_WEBHOOK_URL}`)
- **SOPS Encryption:** `config/secrets.enc.yaml` encrypted at rest (never commit decrypted)
- **No Hardcoded Secrets:** Repository contains zero plaintext credentials

### Feature Gating
- **Live Trading:** Requires `app.env=live` in config AND `NJORD_ENABLE_LIVE=1` env var
- **Metrics Emission:** Gated by `NJORD_ENABLE_METRICS=1` (disabled in tests by default)
- **Alert Notifications:** Gated by `NJORD_ENABLE_ALERTS=1` (disabled in tests by default)

### Kill-Switch Enforcement
- **File-Based:** `/tmp/njord_killswitch` presence trips all services
- **Redis-Based:** `njord:killswitch` key trips all services
- **Process Manager:** Checks kill-switch before starting live services (refuses if tripped)
- **Alert Integration:** Critical alerts fire when kill-switch triggered

## Roadmap Snapshot
- **Phase 0 — Bootstrap & Guardrails:** Tooling, config loader, structured logging, NDJSON journal ✅
- **Phase 1 — Event Bus & Market Data:** Redis bus, contracts, market data ingest daemon ✅
- **Phase 2 — Risk Engine & Paper OMS:** Risk policies, paper trader, kill-switch integrations ✅
- **Phase 3 — Live Broker:** Binance.US adapter with dry-run safeguards and kill-switch enforcement ✅
- **Phase 4 — Market Data Storage:** Persistent OHLCV/tick storage, compression, and replay hooks ✅
- **Phase 5 — Backtester:** Contracts, engine core, fill simulation, equity curve, metrics, CLI, golden tests, parameter sweeps, and reporting ✅
- **Phase 6 — Portfolio Allocator:** Multi-strategy capital allocation, risk adjustment, portfolio backtesting, and reporting ✅
- **Phase 7 — Research API:** Data reader, aggregation stack, research CLI, and documentation ✅
- **Phase 8 — Execution Layer:** TWAP/VWAP/Iceberg/POV algorithms, slippage models, smart order routing 📋
- **Phase 9 — Metrics & Telemetry:** Prometheus exporter, Grafana dashboards, performance attribution, real-time metrics 📋
- **Phase 10 — Live Trade Controller:** Unified CLI (njord-ctl), process management, config hot-reload, session tracking 📋
- **Phase 11 — Monitoring & Alerts:** Alert rules engine, multi-channel notifications, deduplication 📋
- **Phase 12–16:** Compliance & audit, advanced strategies, simulation harness, deployment, optimization 📋

## Support & Licensing
- Maintained by **Njord Trust LLC**.
- Proprietary license; consult organizational policies for usage and distribution rights.
