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
