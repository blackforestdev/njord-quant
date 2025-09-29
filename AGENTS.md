# Njord Quant — Agent Operating Guide

## Mission
Implement **Phase 0 → 1** of Njord Quant in small, reviewable diffs:
- Phase 0.2–0.4: config loader, structured JSON logging, NDJSON journal.
- Phase 1.0–1.1: Redis bus (async), minimal market data ingest (read-only).

## Golden Rules
- **Never** commit secrets. Do not touch `config/secrets.enc.yaml` contents.
- Prefer **small PR-sized changes** (≤ ~150 LOC / 4 files).
- Keep repo green: `make fmt && make lint && make type && make test` must pass.
- Python: **3.11**, `mypy --strict`, `ruff` (see `ruff.toml`), tests via `pytest`.
- Use `from core.contracts import …` (no top-level `contracts` imports).
- New packages must have `__init__.py`.
- Logging: **structlog** to NDJSON files under `var/log/njord/`.
- Journals: NDJSON append-only; rotation by separate script, not inline.

## Output Format
- Always propose a **diff** (unified patch) or **file blocks** with full content.
- Include short rationale + test plan: exact commands and expected outputs.
- If blocked, state the blocker and propose the smallest unblocking change.

## Directory Truth
- Configs: `config/` (not `configs/`).
- Code: `core/`, `apps/`, `risk/`, `strategies/`, `tests/`.
- Make targets: `venv install pre-commit fmt lint type test`.

## Commit Style
Conventional commits:
- `feat(core/logging): structured JSON logging helper + snapshot test`
- `chore(mypy): exclude app __main__ entrypoints temporarily`

## Done Definition (per task)
- New code is typed, linted, tested; `make fmt lint type test` are green.
- Minimal docs in file header if nontrivial behavior exists.
