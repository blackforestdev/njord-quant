# Claude Code Configuration

**This project uses a unified agent directive document.**

👉 **See [AGENTS.md](./AGENTS.md) for complete operating procedures.**

---

## Critical Rules (Enforced)

### 🚨 Before ANY code change:
```bash
make fmt && make lint && make type && make test
```
**All checks must pass (green) before emitting output.**

### 📝 Output Format
- **Unified diffs only** (no prose explanations unless requested)
- Include file paths and line numbers
- Keep changes ≤150 LOC, ≤4 files per commit

### 🔒 Non-Negotiables
- **Never commit secrets** (`config/secrets.enc.yaml`)
- **Never bypass risk/kill-switch** protections
- **Phase integrity:** New code must not break prior phase tests
- **Test performance:** Suite must complete in ≤30 seconds

### 🏗️ Architecture Boundaries
```
Strategy → OrderIntent → Risk Engine → Broker
```
Never let strategies call broker directly.

---

## Current Development Context

**Phase:** 3.8 — Strategy Plugin Framework
**Status:** In Progress
**Python:** 3.11
**Type Checking:** `mypy --strict`
**Linting:** `ruff` (E, F, I, B, UP, SIM, RUF)

### Active Deliverables (Phase 3.8)
- [ ] `strategies/base.py` (ABC with `on_event()`)
- [ ] `strategies/context.py` (injected state container)
- [ ] `strategies/registry.py` (discovery + factory)
- [ ] `strategies/manager.py` (lifecycle management)
- [ ] `config/strategies.yaml` (config schema)
- [ ] Sample strategies: `trendline_break`, `rsi_tema_bb`
- [ ] Golden tests (≤1k JSONL, deterministic)

---

## Quick Fix Patterns

| Issue | Solution |
|-------|----------|
| Import order (I001) | stdlib → third-party → local |
| Missing type hints | Add `-> None`, `-> int`, etc. |
| Abstract method empty (B027) | Use concrete no-op or state flag |
| Test flakiness | Seed RNG, inject `FixedClock`, use `asyncio.Event` |
| Golden test bloat | Keep ≤1k lines, compress or split |

---

## Commit Convention
```
<type>(<scope>): <subject>

Examples:
feat(strategies): add StrategyBase ABC with on_event hook
test(strategies): golden test for trendline_break determinism
fix(broker): handle duplicate clientOrderId idempotently
```

---

## When to Stop and Ask
- Requirements are ambiguous or conflicting
- Breaking changes to existing APIs
- Missing dependencies or tools

**Do NOT invent behaviors not documented in AGENTS.md.**

---

📘 **Full documentation:** [AGENTS.md](./AGENTS.md)
🔧 **Make targets:** See `Makefile` or run `make help`
📦 **Config:** `config/base.yaml`, `config/strategies.yaml`
