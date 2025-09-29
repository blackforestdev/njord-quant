# Njord Quant

Local-first, event-driven trading stack using `ccxt.pro`.
No Docker; `systemd` per service; JSON journaling; strict risk layer.

## Quick start
1) `python3 -m venv venv && source venv/bin/activate`
2) Edit `config/base.yaml` and `config/secrets.enc.yaml`.
3) `make run-md` / `run-strat` / `run-broker` after adding real code.

## Layout
- `apps/*`: daemons (ingest, strategy, risk, broker, portfolio, paper, monitor)
- `core/*`: bus, contracts, time, logging helpers
- `strategies/*`: plugin strategies
- `risk/*`: risk rules/gates
- `backtest/*`: replay and metrics
- `deploy/systemd/*`: unit templates

## Roadmap Progress

### Phase 0 — Bootstrap & Guardrails
- Repo initialized with `pyproject.toml`, `Makefile`, `pre-commit`, `ruff`, `mypy`, and `pytest`.
- Config loader via Pydantic (`core/config.py`).
- Structured JSON logging and `sops` secrets placeholder.
- Base `systemd` unit templates under `systemd/`.

### Phase 1 — Event Bus & Market Data Ingest
- Redis pub/sub wrapper (`core/bus.py`).
- Contracts for `TradeEvent`, `BookEvent`, `TickerEvent`.
- Market data ingest app (`apps/md_ingest`) with NDJSON journaling.
- Reconnect/backoff logic tested; journaling replay verified.

### Phase 2 — Paper OMS, Risk MVP, Kill-switch
- Paper trader (`apps/paper_trader`) with simulated fills.
- Risk engine (`apps/risk_engine`) enforcing notional caps, daily loss caps, and rate guards.
- Global kill-switch (`core/kill_switch.py`) via file or Redis.
- Tests include idempotency, drawdown halts, and kill-switch E2E.

### Phase 3 — Live Broker (Binance.US)
- Live trading only arms when `config.app.env` is `live` and `NJORD_ENABLE_LIVE=1`; otherwise broker stays read-only.
- Kill switches checked before every live order (file + optional Redis).
- $10 hard per-order notional ceiling enforced (`risk.decisions` denial if exceeded).
- Kill switch trips publish `risk.decisions` with reason `kill_switch` and block placements.
- Dry-run mode echoes broker requests to `broker.echo`.

---
