## Phase 0 — Bootstrap & Guardrails ✅

### Phase 0.1 — Project Structure ✅
**Status:** Complete
**Dependencies:** None
**Delivered:** `Makefile`, `pyproject.toml`, `.gitignore`, `ruff.toml`, `mypy.ini`

### Phase 0.2 — Config Loader ✅
**Status:** Complete
**Dependencies:** 0.1
**Task:** Implement Pydantic-based config loader in `core/config.py`
- Read `config/base.yaml` (required)
- Merge `config/secrets.enc.yaml` (optional)
- Validation via `Config.model_validate()`

**Files:**
- `core/config.py` (150 LOC)
- `tests/test_config.py` (3 test cases)

**Acceptance:** `make fmt lint type test` green

---

### Phase 0.3 — Structured Logging ✅
**Status:** Complete
**Dependencies:** 0.2
**Task:** Implement NDJSON logging via `structlog`

**Behavior:**
- `setup_json_logging(log_dir: str)` → configures structlog
- Output to `{log_dir}/app.ndjson`
- ISO timestamps, log levels, structured fields

**Files:**
- `core/logging.py` (60 LOC)
- `tests/test_logging_snapshot.py` (golden test)

**Acceptance:** JSON lines parseable, timestamps present

---

### Phase 0.4 — NDJSON Journal ✅
**Status:** Complete
**Dependencies:** 0.3
**Task:** Create append-only journal writer

**API:**
```python
journal = NdjsonJournal(path)
journal.write_lines(["line1", "line2"])
journal.close()
```

**Files:**
- `core/journal.py` (30 LOC)
- `tests/test_journal_basic.py`

**Acceptance:** Lines appended with newlines, flushed immediately

---
