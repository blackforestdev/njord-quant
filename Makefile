PY := ./venv/bin/python

.PHONY: venv install lint type test run-md run-strat run-broker journal touch

venv:
	@if [ ! -d venv ]; then python3 -m venv venv; fi

install: venv
	@echo "Local-only placeholder. Add pip installs when ready."

lint:
	@echo "ruff placeholder (no external fetch)."

type:
	@echo "mypy placeholder (no external fetch)."

test:
	@./venv/bin/python -m pytest || true

run-md:
	@$(PY) -m apps.md_ingest --config ./config/base.yaml || true

run-strat:
	@$(PY) -m apps.strategy_runner --config ./config/base.yaml || true

run-broker:
	@$(PY) -m apps.broker_binanceus --config ./config/base.yaml || true

journal:
	@mkdir -p data/journal && echo "journals in data/journal"

touch:
	@find . -type d -empty -print -exec touch {}/.keep.filetype \;
