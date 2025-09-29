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

## Phase 3
- Live trading only arms when `config.app.env` is `live` and `NJORD_ENABLE_LIVE=1`; otherwise the broker stays read-only.
- Before live placement, both kill switches are consulted: the file at `risk.kill_switch_file` and the optional Redis key `risk.kill_switch_key`.
- Every live order faces a $10 notional ceiling using the best known trade price (falling back to the intent limit price); violations publish `risk.decisions` denials with reason `live_micro_cap`.
- Kill switch trips publish `risk.decisions` denials with reason `kill_switch` and block placements.
- When running dry, orders map to broker requests and are echoed on the `broker.echo` topic for downstream coordination.
