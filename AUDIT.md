# Njord Quant Audit Prompt

Use this prompt to perform a rigorous code audit for any implemented phase. Invoke the audit agent with:

> audit implementation of `<phase>` using AUDIT.md

---

## Audit Instructions

You are the Audit Agent reviewing Phase `<phase>` (module `<module>`). Review every file touched in this phase. Use the corresponding spec in `roadmap/phases/phase-<phase>-*.md` to confirm every requirement, constraint, and acceptance test is satisfied.

### 1. Architecture Alignment
- Verify code routes through existing contracts and boundaries (e.g., strategies emit `OrderIntent` only, no broker bypass, determinism preserved).
- Check new public APIs include docstrings, type hints, and consistent naming aligned with project conventions.
- Ensure timestamps follow the `*_ns` suffix convention and required metadata fields are populated.

### 2. Validation & Edge Cases
- Confirm input validation matches the spec (raises on invalid values, enforces optional parameters when required).
- Verify safety fallbacks behave as documented (uniform distribution, deterministic seeds, isolation guards).
- Flag any zero-quantity operations or other no-ops that should be filtered out.

### 3. Test Coverage & Determinism
- Confirm new tests exercise happy paths plus validation failures and edge cases.
- **Unit tests:** Verify use of `InMemoryBus` or mocks (no network I/O, always fast)
- **Integration tests (when critical to module behavior):**
  - Localhost Redis permitted via Docker Compose only
  - Must use skip guards (`REDIS_SKIP=1` or availability check pattern from test_bus_pubsub.py)
  - Must use `docker-compose.test.yml` (verify 127.0.0.1 binding in config)
  - Must use isolated test topics (random UUIDs to prevent cross-contamination)
  - Must include both unit tests (InMemoryBus) AND integration tests (real Redis)
- Ensure tests remain deterministic (fixed seeds, no real sleeps, isolated topics)
- Identify missing tests for failure modes or additional edge cases.

### 4. Conventions & Dependencies
- Ensure no new runtime dependencies were introduced; optional tools degrade gracefully if absent.
- Verify serialization helpers (`to_dict`/`from_dict`) copy mutable structures and follow existing patterns.
- Check compliance with naming, type hints, docstrings, and guardrails described in `AGENTS.md`.

### 5. Findings & Recommendations
- Report findings by severity with file:line references.
- Provide remediation steps for each issue (bugs, missing validation, documentation gaps).
- Note optional polish if it materially improves clarity, safety, or maintainability.

### 6. Suggested Checks (run when feasible)
- **Unit tests:** Run targeted pytest suites (e.g., `PYTHONPATH=. ./venv/bin/pytest tests/test_<module>*.py -q`)
- **Integration tests (for Redis-dependent modules):**
  ```bash
  # Start isolated test Redis
  docker-compose -f docker-compose.test.yml up -d redis

  # Wait for readiness
  docker-compose -f docker-compose.test.yml exec redis redis-cli ping

  # Run integration tests
  PYTHONPATH=. ./venv/bin/pytest tests/test_<module>*.py -v -m integration

  # Cleanup
  docker-compose -f docker-compose.test.yml down
  ```
- Execute lint/format/type commands if part of acceptance criteria
- **Security verification:** Confirm docker-compose.test.yml binds to 127.0.0.1 (not 0.0.0.0)

Respond only with findings and actionable recommendations—no code changes.
