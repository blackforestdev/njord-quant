# Njord Quant Development Roadmap

**Current Phase:** 8 — Execution Layer 📋
**Last Updated:** 2025-10-02

## Quick Navigation

- [How to Use This Roadmap](#how-to-use-this-roadmap)
- [Phase Index](#phase-index)
- [Current Phase Details](roadmap/phases/phase-08-execution.md)
- [Dependencies Graph](#dependencies-graph)

---

## How to Use This Roadmap

### For Humans
1. Check "Current Phase" above
2. Browse [Phase Index](#phase-index) below
3. Click phase link to view detailed specification
4. Use `make status` to see current task
5. Use `make next` to see next planned task

### For AI Agents
1. Read this index file (ROADMAP.md) to find current phase
2. Open corresponding phase file: `roadmap/phases/phase-XX-name.md`
3. Navigate to specific sub-phase
4. Execute per acceptance criteria
5. Update status emoji (📋 → 🚧 → ✅)

**Token Optimization:**
- Read ROADMAP.md (500 lines) → identify phase
- Read specific phase file (800-1500 lines) → find sub-phase
- **Total: ~2000 lines vs 9000 (78% reduction)**

---

## Phase Index

| Phase | Title | Status | Sub-Phases | Link |
|-------|-------|--------|------------|------|
| 0 | Bootstrap & Guardrails | ✅ | 4 | [phase-00-bootstrap.md](roadmap/phases/phase-00-bootstrap.md) |
| 1 | Event Bus & Market Data | ✅ | 5 | [phase-01-event-bus.md](roadmap/phases/phase-01-event-bus.md) |
| 2 | Risk Engine & Paper OMS | ✅ | 6 | [phase-02-risk-paper.md](roadmap/phases/phase-02-risk-paper.md) |
| 3 | Strategy Plugin Framework | ✅ | 8 | [phase-03-live.md](roadmap/phases/phase-03-live.md) |
| 4 | Market Data Storage | ✅ | 4 | [phase-04-market-data.md](roadmap/phases/phase-04-market-data.md) |
| 5 | Backtester | ✅ | 5 | [phase-05-backtester.md](roadmap/phases/phase-05-backtester.md) |
| 6 | Portfolio Allocator | ✅ | 4 | [phase-06-portfolio.md](roadmap/phases/phase-06-portfolio.md) |
| 7 | Research API | ✅ | 9 | [phase-07-research-api.md](roadmap/phases/phase-07-research-api.md) |
| 8 | Execution Layer | 📋 | 9 | [phase-08-execution.md](roadmap/phases/phase-08-execution.md) |
| 9 | Metrics & Telemetry | 📋 | 10 | [phase-09-telemetry.md](roadmap/phases/phase-09-telemetry.md) |
| 10 | Live Trade Controller | 📋 | 8 | [phase-10-controller.md](roadmap/phases/phase-10-controller.md) |
| 11 | Monitoring & Alerts | 📋 | 10 | [phase-11-monitoring.md](roadmap/phases/phase-11-monitoring.md) |
| 12 | Compliance & Audit | 📋 | 9 | [phase-12-compliance.md](roadmap/phases/phase-12-compliance.md) |
| 13 | Advanced Strategy Toolkit | 📋 | 10 | [phase-13-strategies.md](roadmap/phases/phase-13-strategies.md) |

---

## Dependencies Graph

```
Phase 0 (Bootstrap) ✅
    └─> Phase 1 (Event Bus) ✅
            └─> Phase 2 (Risk & Paper) ✅
                    └─> Phase 3 (Strategy Framework) ✅
                            └─> Phase 4 (Market Data) ✅
                                    └─> Phase 5 (Backtester) ✅
                                            └─> Phase 6 (Portfolio) ✅
                                                    └─> Phase 7 (Research) ✅
                                                            └─> Phase 8 (Execution) 📋
                                                                    └─> Phase 9 (Telemetry) 📋
                                                                            └─> Phase 10 (Controller) 📋
                                                                                    └─> Phase 11 (Monitoring) 📋
                                                                                            └─> Phase 12 (Compliance) 📋
                                                                                                    └─> Phase 13 (Strategies) 📋
```

---

## Current Phase Summary

**Phase 8 — Execution Layer** 📋

Implement sophisticated order execution algorithms, smart routing, and realistic slippage/fee simulation.

**Sub-Phases:**
- 8.0: Execution Layer Foundations (BusProto, BaseExecutor, adapters)
- 8.1: Execution Contracts (ExecutionAlgorithm, ExecutionSlice, ExecutionReport)
- 8.2: TWAP Algorithm (Time-Weighted Average Price)
- 8.3: VWAP Algorithm (Volume-Weighted Average Price)
- 8.4: Iceberg Algorithm (Hidden order display)
- 8.5: POV Algorithm (Percentage of Volume)
- 8.6: Slippage Models (Linear, square-root market impact)
- 8.7: Smart Order Router (Algorithm selection logic)
- 8.8: Execution Simulator (Backtest integration)
- 8.9: Execution Performance Metrics (Implementation shortfall, slippage tracking)

**Full Details:** [roadmap/phases/phase-08-execution.md](roadmap/phases/phase-08-execution.md)

**Note:** Phases 8-13 have detailed specifications but are not yet implemented. Implementation follows dependency order (8 → 9 → 10 → 11 → 12 → 13).

---

## Status Legend

| Emoji | Meaning |
|-------|---------|
| ✅ | Complete (all tests passing) |
| 🚧 | In Progress (partial implementation) |
| 📋 | Planned (not started) |
| ⚠️ | Blocked (dependency issue) |
| 🔄 | Rework Needed (failing tests/review) |

---

## Make Targets

```bash
# View this index
make roadmap

# Show current phase status
make status

# Show next planned task
make next

# Open current phase file directly
make phase-current

# Open specific phase file
make phase NUM=13
```

---

## Documentation Hierarchy

1. **[ROADMAP.md](./ROADMAP.md)** (this file) — Phase index and navigation
2. **[roadmap/phases/*.md](./roadmap/phases/)** — Detailed phase specifications
3. **[AGENTS.md](./AGENTS.md)** — Strategic operating procedures and coding standards
4. **[CLAUDE.md](./CLAUDE.md)** — Claude Code entry point

**For task execution:** Always consult phase files for detailed behavioral specifications, acceptance criteria, and file locations. This index defines *what phases exist*; phase files define *what to build next*.

---

## Migration Notes

**What Changed (2025-10-02):**
- Split monolithic 9000-line ROADMAP.md into 14 phase files
- Created hierarchical structure: `roadmap/phases/phase-XX-name.md`
- Original preserved: `roadmap/archive/ROADMAP-monolith.md`
- Token efficiency: 78% reduction for agent interactions

**Backwards Compatibility:**
- `make status` and `make next` continue to work (updated scripts)
- All phase content preserved (no information loss)
- Phase numbers and titles unchanged
- Status tracking (✅/🚧/📋) preserved

**Rollback Procedure:**
If needed: `cp roadmap/archive/ROADMAP-monolith.md ROADMAP.md`

---

**Last Updated:** 2025-10-02
**Maintained By:** Njord Trust
**License:** Proprietary
