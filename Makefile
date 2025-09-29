# Makefile — guardrails 0.1 using ./venv
PY       := ./venv/bin/python
PIP      := ./venv/bin/pip
PRECOMMIT:= ./venv/bin/pre-commit
CONFIG_ROOT ?= .

.DEFAULT_GOAL := help

.PHONY: help venv install pre-commit fmt lint type test run-md run-strat run-broker run-risk run-paper run-kill-trip run-kill-clear check-kill journal touch

help:
	@echo "Targets:"
	@echo "  venv         - create ./venv"
	@echo "  install      - install dev tools (ruff, mypy, pytest, pre-commit)"
	@echo "  pre-commit   - install git hook"
	@echo "  fmt|lint|type|test - guardrails"
	@echo "  run-md|run-strat|run-broker|run-risk|run-paper - app runners"
	@echo "  run-kill-trip|run-kill-clear|check-kill - kill switch helpers"
	@echo "  journal      - make data/journal"
	@echo "  touch        - drop .keep.filetype in empty dirs"

venv:
	@if [ ! -d venv ]; then python3 -m venv venv; fi
	@echo "[ok] venv at ./venv"

install: venv
	$(PIP) install -U pip wheel
	$(PIP) install ruff mypy pytest pytest-asyncio pre-commit
	@echo "[ok] dev tools installed"

pre-commit:
	$(PRECOMMIT) install
	@echo "[ok] pre-commit hook installed"

fmt:
	./venv/bin/ruff format .

lint:
	./venv/bin/ruff check .

type:
	./venv/bin/mypy .

test:
	$(PY) -m pytest -q

run-md:
	@if [ -z "$(SYMBOL)" ] || [ -z "$(VENUE)" ]; then \
		echo "Usage: make run-md SYMBOL=ATOM/USDT VENUE=binanceus"; \
		exit 1; \
	fi
	$(PY) -m apps.md_ingest --symbol $(SYMBOL) --venue $(VENUE) --config-root $(CONFIG_ROOT)

run-strat:
	$(PY) -m apps.strategy_runner --config ./config/base.yaml || true

run-broker:
	$(PY) -m apps.broker_binanceus.main --config-root $(CONFIG_ROOT) || true

run-risk:
	$(PY) -m apps.risk_engine.main --config-root $(CONFIG_ROOT) || true

run-paper:
	$(PY) -m apps.paper_trader.main --config-root $(CONFIG_ROOT) || true

run-kill-trip:
	$(PY) scripts/njord_kill.py --config-root $(CONFIG_ROOT) trip-file

run-kill-clear:
	$(PY) scripts/njord_kill.py --config-root $(CONFIG_ROOT) clear-file

check-kill:
	$(PY) scripts/njord_kill.py --config-root $(CONFIG_ROOT) check

journal:
	mkdir -p data/journal && echo "journals in data/journal"

touch:
	find . -type d -empty -print -exec touch {}/.keep.filetype \;
