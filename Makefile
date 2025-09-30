# Makefile — guardrails 0.1 using ./venv
PY       := ./venv/bin/python
PIP      := ./venv/bin/pip
PRECOMMIT:= ./venv/bin/pre-commit
CONFIG_ROOT ?= .

.DEFAULT_GOAL := help

.PHONY: help venv install pre-commit fmt lint type test roadmap status next run-md run-strat run-broker run-risk run-paper run-kill-trip run-kill-clear check-kill journal touch

help:
	@echo "Njord Quant — Development Targets"
	@echo ""
	@echo "Setup & Tools:"
	@echo "  venv         - create ./venv"
	@echo "  install      - install dev tools (ruff, mypy, pytest, pre-commit)"
	@echo "  pre-commit   - install git hook"
	@echo ""
	@echo "Code Quality (Guardrails):"
	@echo "  fmt          - format code with ruff"
	@echo "  lint         - lint code with ruff"
	@echo "  type         - type-check with mypy"
	@echo "  test         - run tests with pytest"
	@echo ""
	@echo "Roadmap & Planning:"
	@echo "  roadmap      - view full development roadmap"
	@echo "  status       - show current phase task status"
	@echo "  next         - show next planned task"
	@echo ""
	@echo "Service Runners:"
	@echo "  run-md       - start market data ingest (requires SYMBOL and VENUE)"
	@echo "  run-strat    - start strategy runner"
	@echo "  run-broker   - start broker service"
	@echo "  run-risk     - start risk engine"
	@echo "  run-paper    - start paper trader"
	@echo ""
	@echo "Kill Switch:"
	@echo "  run-kill-trip  - trip kill switch (file)"
	@echo "  run-kill-clear - clear kill switch (file)"
	@echo "  check-kill     - check kill switch status"
	@echo ""
	@echo "Utilities:"
	@echo "  journal      - create data/journal directory"
	@echo "  touch        - add .keep.filetype to empty dirs"
	@echo ""
	@echo "Usage Examples:"
	@echo "  make run-md SYMBOL=ATOM/USDT VENUE=binanceus"
	@echo "  make fmt && make lint && make type && make test"

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

# Roadmap navigation targets
roadmap:
	@if [ ! -f ROADMAP.md ]; then \
		echo "Error: ROADMAP.md not found"; \
		exit 1; \
	fi
	@echo "📋 Opening ROADMAP.md..."
	@less ROADMAP.md

status:
	@if [ ! -f ROADMAP.md ]; then \
		echo "Error: ROADMAP.md not found"; \
		exit 1; \
	fi
	@echo "📊 Current Phase Status (Phase 3.8):"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@grep -E "^#### Task 3\.8\.[0-9]" ROADMAP.md | head -10 || echo "No tasks found for Phase 3.8"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "Legend: ✅ Complete | 🚧 In Progress | 📋 Planned | ⚠️ Blocked | 🔄 Rework"
	@echo ""
	@echo "For full details: make roadmap"

next:
	@if [ ! -f ROADMAP.md ]; then \
		echo "Error: ROADMAP.md not found"; \
		exit 1; \
	fi
	@echo "🎯 Next Planned Task:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@grep -A 20 "📋" ROADMAP.md | head -25 || echo "No planned tasks found"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "To implement: Review task in ROADMAP.md, then run:"
	@echo "  make fmt && make lint && make type && make test"

# Service runners
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

# Kill switch helpers
run-kill-trip:
	$(PY) scripts/njord_kill.py --config-root $(CONFIG_ROOT) trip-file

run-kill-clear:
	$(PY) scripts/njord_kill.py --config-root $(CONFIG_ROOT) clear-file

check-kill:
	$(PY) scripts/njord_kill.py --config-root $(CONFIG_ROOT) check

# Utilities
journal:
	mkdir -p data/journal && echo "journals in data/journal"

touch:
	find . -type d -empty -print -exec touch {}/.keep.filetype \;
