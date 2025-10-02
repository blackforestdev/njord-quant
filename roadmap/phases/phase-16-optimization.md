## Phase 16 — Optimization Pass 📋

**Purpose:** Final optimization, profiling, code cleanup, and comprehensive documentation to achieve production-ready status.

**Current Status:** Phase 15 complete — Deployment Framework fully operational
**Next Phase:** Production-ready system (COMPLETE)

---

### Phase 16.0 — Performance Profiling 📋
**Status:** Planned
**Dependencies:** 15.7 (Deployment Documentation)
**Task:** Profile CPU and memory usage, identify bottlenecks

**Critical Architectural Requirements:**
1. **Minimal Overhead:** Profiling must not degrade performance >5%
2. **Production Safety:** Profiling tools safe for live environments
3. **Actionable Results:** Identify top-N bottlenecks with fix recommendations
4. **Deterministic Profiling:** Reproducible results with controlled workload
5. **No Data Leaks:** Profiling output sanitized (no secrets in profiles)

**Deliverables:**

#### 1. CPU Profiling Setup
```python
# scripts/profile_cpu.py
"""CPU profiling utility using cProfile and py-spy.

Usage:
    # Profile specific service
    python scripts/profile_cpu.py --service risk_engine --duration 60

    # Generate flamegraph
    py-spy record -o flamegraph.svg --pid <PID> --duration 60
"""

import cProfile
import pstats
from pathlib import Path

def profile_service(
    service_module: str,
    duration_seconds: int,
    output_dir: Path = Path("var/profiling")
) -> None:
    """Profile service for specified duration.

    Args:
        service_module: Module to profile (e.g., "apps.risk_engine")
        duration_seconds: Profiling duration
        output_dir: Output directory for profile data

    Generates:
        - profile.stats: cProfile statistics
        - profile.txt: Human-readable profile report
        - flamegraph.svg: Flame graph visualization (if py-spy available)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    profiler = cProfile.Profile()
    profiler.enable()

    # Run service for duration
    # ... service execution ...

    profiler.disable()

    # Save statistics
    stats_file = output_dir / "profile.stats"
    profiler.dump_stats(stats_file)

    # Generate report
    stats = pstats.Stats(profiler, stream=sys.stdout)
    stats.sort_stats("cumulative")
    with open(output_dir / "profile.txt", "w") as f:
        stats.print_stats(20)  # Top 20 functions

def analyze_hotspots(stats_file: Path) -> list[dict[str, Any]]:
    """Analyze profile and identify hotspots.

    Returns:
        List of hotspots with:
        - function_name: str
        - cumulative_time: float
        - percent_total: float
        - call_count: int
        - optimization_priority: Literal["high", "medium", "low"]
    """
    pass
```

#### 2. Memory Profiling Setup
```python
# scripts/profile_memory.py
"""Memory profiling utility using memory_profiler and tracemalloc.

Usage:
    # Profile memory usage
    python scripts/profile_memory.py --service paper_trader --duration 60

    # Track memory leaks
    python scripts/profile_memory.py --service broker --leak-detection
"""

import tracemalloc
from memory_profiler import profile

def profile_memory(
    service_module: str,
    duration_seconds: int,
    leak_detection: bool = False
) -> dict[str, Any]:
    """Profile memory usage and detect leaks.

    Returns:
        {
            "peak_memory_mb": float,
            "current_memory_mb": float,
            "leaked_objects": list[dict] if leak_detection else None,
            "top_allocations": list[dict]  # Top 10 memory allocations
        }
    """
    tracemalloc.start()

    # Run service for duration
    # ...

    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")

    # Detect leaks by comparing snapshots over time
    if leak_detection:
        # Compare with earlier snapshot
        pass

    return {
        "peak_memory_mb": tracemalloc.get_traced_memory()[1] / 1024 / 1024,
        "top_allocations": [
            {
                "file": stat.traceback.format()[0],
                "size_mb": stat.size / 1024 / 1024,
                "count": stat.count
            }
            for stat in top_stats[:10]
        ]
    }
```

**Files:**
- `scripts/profile_cpu.py` (CPU profiling, ~200 LOC)
- `scripts/profile_memory.py` (Memory profiling, ~180 LOC)
- `scripts/analyze_profiles.py` (Profile analysis, ~150 LOC)
- `docs/profiling/PROFILING.md` (Profiling guide, ~200 lines)
- `tests/test_profiling.py`

**Acceptance:**
- CPU profiler identifies top 20 functions by cumulative time
- Memory profiler tracks peak memory and top allocations
- Leak detection compares snapshots over time
- **Test verifies profiling overhead <5% (compare with/without profiling)**
- **Test verifies hotspot analysis identifies known bottleneck**
- **Test verifies memory leak detection (inject artificial leak)**
- PROFILING.md includes interpretation guide for profile data
- `make fmt lint type test` green

---

### Phase 16.1 — Event Loop Optimization 📋
**Status:** Planned
**Dependencies:** 16.0 (Performance Profiling)
**Task:** Optimize async event loops, reduce latency, improve throughput

**Behavior:**
- Profile event loop lag and task scheduling
- Optimize blocking operations (move to thread pool)
- Reduce unnecessary async/await overhead
- Batch Redis pub/sub operations where possible
- Tune asyncio event loop parameters

**Optimization Targets:**
```python
# Before optimization
async def on_trade(self, trade: TradeEvent) -> None:
    # Blocking operations in event loop
    position = self.db.get_position(trade.symbol)  # BLOCKS!
    await self.bus.publish_json("positions.update", position.to_dict())

# After optimization
async def on_trade(self, trade: TradeEvent) -> None:
    # Non-blocking with thread pool for DB access
    position = await asyncio.get_event_loop().run_in_executor(
        self.executor,
        self.db.get_position,
        trade.symbol
    )
    await self.bus.publish_json("positions.update", position.to_dict())
```

**Batching Optimization:**
```python
# Before: Individual publishes (high overhead)
for intent in intents:
    await self.bus.publish_json("strat.intent", intent.to_dict())

# After: Batch publish (lower overhead)
await self.bus.publish_batch(
    "strat.intent",
    [intent.to_dict() for intent in intents]
)
```

**Requirements:**
- Identify and fix blocking operations in event loop
- Implement batch operations for high-frequency events
- Reduce event loop lag to <1ms p99
- Improve throughput by 20-50% for high-load scenarios
- Maintain correctness (no race conditions introduced)

**Constraints:**
- No new runtime dependencies
- Backwards compatible (existing code continues to work)
- Maintain determinism in tests

**Files:**
- `core/bus.py` (add publish_batch method, ~30 LOC)
- Optimization patches in service files (~10-20 LOC each)
- `docs/profiling/OPTIMIZATION_REPORT.md` (Before/after metrics, ~150 lines)
- `tests/test_event_loop_perf.py` (Performance regression tests)

**Acceptance:**
- Blocking operations moved to thread pool (test verifies no blocking)
- Batch publish operations implemented and tested
- Event loop lag reduced to <1ms p99 (benchmark test)
- **Performance test: 1000 events/sec throughput sustained**
- **Test verifies no race conditions introduced (concurrent stress test)**
- OPTIMIZATION_REPORT.md shows before/after latency percentiles
- `make fmt lint type test` green

---

### Phase 16.2 — Memory Optimization 📋
**Status:** Planned
**Dependencies:** 16.1 (Event Loop Optimization)
**Task:** Reduce memory footprint, fix memory leaks, optimize data structures

**Behavior:**
- Fix identified memory leaks (from profiling)
- Replace inefficient data structures (e.g., list → deque for bounded queues)
- Implement object pooling for high-churn objects
- Add memory limits and backpressure mechanisms
- Optimize dataclass memory usage (slots)

**Optimization Targets:**
```python
# Before: High memory churn
class MarketDataCache:
    def __init__(self):
        self.trades: list[TradeEvent] = []  # Unbounded list

    def add_trade(self, trade: TradeEvent):
        self.trades.append(trade)  # Memory leak!

# After: Bounded with deque
from collections import deque

class MarketDataCache:
    def __init__(self, max_size: int = 10000):
        self.trades: deque[TradeEvent] = deque(maxlen=max_size)

    def add_trade(self, trade: TradeEvent):
        self.trades.append(trade)  # Auto-evicts oldest
```

**Dataclass Optimization:**
```python
# Before: Default dataclass (dict-based __dict__)
@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    symbol: str
    side: str
    # ... 10+ fields

# After: Slotted dataclass (40% memory reduction)
@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    symbol: str
    side: str
    # ... 10+ fields
```

**Requirements:**
- Fix all memory leaks identified in profiling
- Replace unbounded data structures with bounded equivalents
- Add slots to all hot-path dataclasses
- Reduce peak memory by 20-30%
- Implement backpressure for event streams

**Constraints:**
- Backwards compatible (existing code continues to work)
- No functional changes (only memory optimizations)
- Maintain determinism in tests

**Files:**
- `core/contracts.py` (add slots to dataclasses, ~20 LOC changed)
- `core/cache.py` (bounded cache implementations, ~150 LOC)
- Memory optimization patches in service files (~10-20 LOC each)
- `tests/test_memory_limits.py` (Memory regression tests)

**Acceptance:**
- All identified memory leaks fixed (test with leak detector)
- Unbounded data structures replaced with bounded equivalents
- Dataclasses use slots (verify with sys.getsizeof)
- **Memory test: Peak memory reduced by 20-30% (before/after benchmark)**
- **Test verifies backpressure: event queue blocks when full**
- **Test verifies no memory leaks over 1-hour run**
- `make fmt lint type test` green

---

### Phase 16.3 — Code Cleanup & Refactoring 📋
**Status:** Planned
**Dependencies:** 16.2 (Memory Optimization)
**Task:** Remove dead code, consolidate duplicates, improve code quality

**Behavior:**
- Identify and remove dead code (unused functions, imports)
- Consolidate duplicate logic into shared utilities
- Refactor complex functions (cyclomatic complexity >10)
- Improve naming consistency
- Add missing type hints and docstrings

**Cleanup Targets:**
```python
# Before: Duplicate logic across services
# apps/risk_engine.py
def parse_timestamp(ts_str: str) -> int:
    return int(datetime.fromisoformat(ts_str).timestamp() * 1e9)

# apps/paper_trader.py
def parse_timestamp(ts_str: str) -> int:
    return int(datetime.fromisoformat(ts_str).timestamp() * 1e9)

# After: Consolidated utility
# core/time_utils.py
def parse_timestamp(ts_str: str) -> int:
    """Parse ISO 8601 timestamp to nanoseconds since epoch."""
    return int(datetime.fromisoformat(ts_str).timestamp() * 1e9)
```

**Dead Code Detection:**
```python
# Use coverage.py to find untested code
# Use vulture to find unused code

import vulture

v = vulture.Vulture()
v.scavenge(["core/", "apps/", "strategies/"])
for item in v.get_unused_code():
    print(f"Unused: {item.filename}:{item.lineno} {item.name}")
```

**Requirements:**
- Remove all dead code (0% unused code)
- Consolidate duplicates (max 3 occurrences of similar logic)
- Refactor complex functions (cyclomatic complexity ≤10)
- 100% type hint coverage (mypy --strict passes)
- All public functions have docstrings

**Constraints:**
- No functional changes (only refactoring)
- All tests must still pass
- Backwards compatible

**Files:**
- Code changes across multiple modules (~500 LOC net reduction)
- `scripts/find_dead_code.py` (Dead code detection, ~100 LOC)
- `scripts/find_duplicates.py` (Duplicate detection, ~120 LOC)
- `docs/refactoring/CLEANUP_REPORT.md` (Cleanup summary, ~200 lines)

**Acceptance:**
- Dead code removed (vulture reports 0 unused)
- Duplicate logic consolidated (test with duplicate detector)
- Complex functions refactored (radon reports complexity ≤10)
- **Type hint coverage 100% (mypy --strict passes with no errors)**
- **Docstring coverage 100% for public APIs (interrogate tool)**
- **Code quality improved: ruff check shows fewer issues**
- CLEANUP_REPORT.md documents all changes and justifications
- `make fmt lint type test` green

---

### Phase 16.4 — Test Suite Optimization 📋
**Status:** Planned
**Dependencies:** 16.3 (Code Cleanup)
**Task:** Speed up test suite, improve test coverage, add missing tests

**Behavior:**
- Identify and optimize slow tests
- Parallelize independent test suites
- Reduce test flakiness (eliminate race conditions)
- Add missing edge case tests
- Improve test coverage to 90%+

**Test Optimization:**
```python
# Before: Slow test with real sleep
def test_timeout_behavior():
    start = time.time()
    result = wait_with_timeout(duration=5.0)
    assert time.time() - start >= 5.0

# After: Fast test with mock time
def test_timeout_behavior(mocker):
    mock_sleep = mocker.patch("time.sleep")
    result = wait_with_timeout(duration=5.0)
    mock_sleep.assert_called_once_with(5.0)
```

**Parallelization:**
```bash
# Before: Sequential test execution (slow)
pytest tests/

# After: Parallel execution with pytest-xdist
pytest tests/ -n auto  # Use all CPU cores
```

**Requirements:**
- Test suite completes in ≤30 seconds (was ≤30s already, maintain)
- Test coverage ≥90% (branch coverage)
- Zero flaky tests (100 consecutive runs pass)
- All edge cases covered (negative tests, boundary conditions)
- Golden tests updated if behavior changed

**Constraints:**
- Tests remain deterministic
- No network I/O in tests
- Tests pass in parallel (no shared state)

**Files:**
- Test optimizations across test files (~100 LOC changed)
- `pytest.ini` (add parallelization config, ~10 lines)
- `tests/test_edge_cases.py` (New edge case tests, ~300 LOC)
- `.coveragerc` (Coverage configuration, ~30 lines)

**Acceptance:**
- Test suite completes in ≤30 seconds (pytest duration report)
- Test coverage ≥90% (pytest-cov report)
- Zero flaky tests (100 consecutive runs all pass)
- **Performance test: parallel tests 3-4x faster than sequential**
- **Coverage test: all modules ≥85% coverage**
- **Flakiness test: 1000 consecutive runs with random seeds all pass**
- `make fmt lint type test` green

---

### Phase 16.5 — API Documentation 📋
**Status:** Planned
**Dependencies:** 16.4 (Test Suite Optimization)
**Task:** Generate comprehensive API documentation with examples

**Deliverables:**

#### 1. API Reference (Auto-Generated)
Use Sphinx or mkdocs to generate API docs from docstrings:

```python
# Example docstring format (Google style)
def place_order(
    symbol: str,
    side: Literal["buy", "sell"],
    quantity: float,
    order_type: Literal["market", "limit"] = "market",
    limit_price: float | None = None
) -> OrderAck:
    """Place an order on the exchange.

    Args:
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        side: Order side (buy or sell)
        quantity: Order quantity in base currency
        order_type: Market or limit order (default: market)
        limit_price: Limit price (required if order_type="limit")

    Returns:
        OrderAck with order ID and status

    Raises:
        BrokerError: If order placement fails
        ValueError: If limit_price missing for limit order

    Example:
        >>> ack = place_order("BTC/USDT", "buy", 0.001, order_type="limit", limit_price=50000)
        >>> print(ack.order_id)
        "ord_abc123"

    Note:
        Limit orders require limit_price parameter.
        Market orders execute immediately at best available price.
    """
    pass
```

#### 2. Documentation Structure
```
docs/api/
├── index.md                    # API overview
├── core/
│   ├── bus.md                  # Bus API reference
│   ├── config.md               # Config API reference
│   ├── contracts.md            # Contract types reference
│   └── logging.md              # Logging API reference
├── apps/
│   ├── risk_engine.md          # Risk engine API
│   ├── paper_trader.md         # Paper trader API
│   └── broker.md               # Broker API
├── strategies/
│   ├── base.md                 # Strategy base class
│   ├── context.md              # Strategy context
│   └── registry.md             # Strategy registry
├── backtest/
│   ├── engine.md               # Backtest engine API
│   ├── metrics.md              # Metrics API
│   └── reporting.md            # Reporting API
└── examples/
    ├── custom_strategy.md      # Build custom strategy
    ├── backtest_workflow.md    # Run backtest
    └── live_deployment.md      # Deploy to production
```

**Files:**
- `docs/api/index.md` (API overview, ~150 lines)
- Auto-generated API reference (one file per module, ~100-300 lines each)
- `docs/api/examples/*.md` (Example guides, ~200-400 lines each)
- `mkdocs.yml` or `conf.py` (Documentation build config, ~100 lines)

**Acceptance:**
- All public APIs documented with docstrings
- API reference auto-generated from docstrings
- All examples are runnable (tested in CI)
- **Documentation builds without errors (mkdocs build or sphinx-build)**
- **All code snippets in docs are valid (doctest passes)**
- **Search functionality works (test mkdocs search)**
- Cross-references between docs are accurate
- `make fmt lint type test` green (no code changes)

---

### Phase 16.6 — Operator Manual 📋
**Status:** Planned
**Dependencies:** 16.5 (API Documentation)
**Task:** Create comprehensive operator manual for production use

**Deliverables:**

#### 1. Operator Manual Structure
**File:** `docs/OPERATOR_MANUAL.md`

Sections:
1. **System Overview:**
   - Architecture diagram
   - Service dependencies
   - Data flow
   - Component responsibilities

2. **Installation & Deployment:**
   - Prerequisites
   - Installation procedures (reference Phase 15 docs)
   - Configuration guide
   - Verification steps

3. **Operations:**
   - Starting/stopping services
   - Monitoring dashboards
   - Log analysis
   - Performance tuning

4. **Configuration Reference:**
   - All configuration parameters documented
   - Default values and ranges
   - Security considerations
   - Performance implications

5. **Troubleshooting:**
   - Common issues and solutions
   - Diagnostic procedures
   - Emergency procedures (kill-switch, position liquidation)
   - Support escalation

6. **Maintenance:**
   - Routine maintenance tasks
   - Dependency updates
   - Backup procedures
   - Performance optimization

7. **Security:**
   - Authentication and authorization
   - Secret management
   - Network security
   - Audit logging

8. **Appendices:**
   - Configuration schema
   - API endpoint reference
   - Glossary of terms
   - FAQ

**Files:**
- `docs/OPERATOR_MANUAL.md` (~1500 lines)
- `docs/diagrams/architecture.svg` (Architecture diagram)
- `docs/diagrams/data_flow.svg` (Data flow diagram)
- `docs/appendix/CONFIG_SCHEMA.md` (Config reference, ~400 lines)
- `docs/appendix/GLOSSARY.md` (Glossary, ~200 lines)
- `docs/appendix/FAQ.md` (FAQ, ~300 lines)

**Acceptance:**
- OPERATOR_MANUAL.md covers all 8 sections comprehensively
- Architecture diagrams accurate and up-to-date
- All configuration parameters documented with defaults
- Troubleshooting section addresses all known issues
- **Manual validated by external operator (simulate fresh deployment)**
- **All links and cross-references work correctly**
- **Diagrams generated from source (e.g., PlantUML, Mermaid)**
- `make fmt lint type test` green (no code changes)

---

### Phase 16.7 — Final Validation & Sign-Off 📋
**Status:** Planned
**Dependencies:** 16.6 (Operator Manual)
**Task:** Comprehensive validation of entire system for production readiness

**Validation Checklist:**

#### 1. Functional Validation
- [ ] All phases 0-15 complete with ✅ status
- [ ] All acceptance criteria met
- [ ] All tests passing (unit, integration, golden, simulation)
- [ ] All guardrails green (fmt, lint, type, test)

#### 2. Performance Validation
- [ ] Event loop latency <1ms p99
- [ ] Test suite completes in ≤30 seconds
- [ ] Memory usage within budgets (see Phase 16.2)
- [ ] Throughput targets met (1000+ events/sec)

#### 3. Security Validation
- [ ] No secrets in codebase (git history clean)
- [ ] SOPS encryption working
- [ ] Service isolation enforced (systemd security)
- [ ] Kill-switch functional (file and Redis)
- [ ] Audit logging operational

#### 4. Documentation Validation
- [ ] All documentation complete and accurate
- [ ] API reference generated successfully
- [ ] Operator manual validated by external reviewer
- [ ] Deployment guide tested on clean host
- [ ] Runbooks validated by operations team

#### 5. Deployment Validation
- [ ] Manual deployment successful
- [ ] Ansible deployment successful (if applicable)
- [ ] Health checks passing
- [ ] Monitoring dashboards operational
- [ ] Alerts configured and tested

#### 6. Operational Validation
- [ ] Backup/restore tested successfully
- [ ] Disaster recovery procedure validated
- [ ] Incident response procedures tested
- [ ] Kill-switch drill conducted
- [ ] Service restart procedures validated

**Deliverables:**

#### Sign-Off Report
**File:** `docs/PRODUCTION_READINESS.md`

```markdown
# Production Readiness Sign-Off

**Version:** v1.0.0
**Date:** 2025-10-15
**Reviewed By:** [Operations Team, Security Team, Engineering Team]

## Executive Summary
Njord Quant trading system has completed all 16 development phases and passed comprehensive validation for production deployment.

## Validation Results

### Functional Validation: ✅ PASS
- All phases complete
- All tests passing (489/489)
- All guardrails green

### Performance Validation: ✅ PASS
- Event loop latency: 0.3ms p99 (target: <1ms)
- Test suite duration: 24s (target: ≤30s)
- Peak memory: 380MB (target: <500MB)
- Throughput: 1850 events/sec (target: >1000)

### Security Validation: ✅ PASS
- Secret scanning: No leaks detected
- Service isolation: Enforced
- Kill-switch: Functional (tested)
- Audit logging: Operational

### Documentation Validation: ✅ PASS
- API documentation complete (95% coverage)
- Operator manual validated
- Deployment guide tested
- Runbooks validated

### Deployment Validation: ✅ PASS
- Manual deployment successful (3/3 hosts)
- Ansible deployment successful (if applicable)
- Health checks passing
- Monitoring operational

### Operational Validation: ✅ PASS
- Backup/restore tested: ✅
- Disaster recovery validated: ✅
- Kill-switch drill conducted: ✅
- Service restart validated: ✅

## Known Limitations
[Document any known limitations or deferred features]

## Production Approval
- [ ] Operations Team: _________________ Date: _______
- [ ] Security Team: _________________ Date: _______
- [ ] Engineering Lead: _________________ Date: _______

## Next Steps
1. Schedule production deployment
2. Execute deployment plan
3. Monitor for 48 hours
4. Conduct post-deployment review
```

**Files:**
- `docs/PRODUCTION_READINESS.md` (Sign-off report, ~300 lines)
- `docs/validation/VALIDATION_RESULTS.md` (Detailed validation data, ~500 lines)
- `docs/validation/KNOWN_ISSUES.md` (Known issues and mitigations, ~200 lines)

**Acceptance:**
- All 6 validation categories complete with PASS
- Production readiness report signed off by all stakeholders
- Known limitations documented with mitigations
- **Full system test: 24-hour continuous run with no failures**
- **Stress test: System handles 2x expected load**
- **Security audit: No critical or high-severity issues**
- **Documentation review: External reviewer validates completeness**
- `make fmt lint type test` green

---

**Phase 16 Acceptance Criteria:**
- [ ] All 7 tasks completed (16.0-16.7)
- [ ] `make fmt lint type test` green
- [ ] Performance targets met:
  - Event loop latency <1ms p99
  - Test suite ≤30 seconds
  - Memory reduced by 20-30%
  - Throughput >1000 events/sec
- [ ] Code quality improved:
  - Dead code removed (0% unused)
  - Duplicates consolidated
  - Complexity ≤10 (all functions)
  - Type hint coverage 100%
  - Docstring coverage 100%
- [ ] Test suite optimized:
  - Coverage ≥90%
  - Zero flaky tests
  - Parallel execution working
- [ ] Documentation complete:
  - API reference generated
  - Operator manual comprehensive
  - All guides validated
- [ ] Production validation passed:
  - All 6 validation categories: ✅ PASS
  - Sign-off report approved
  - 24-hour continuous run successful

---

## Integration with Existing System

### Optimization Flow
```
Profiling (16.0)
    ↓
Identify Bottlenecks
    ↓
Event Loop Optimization (16.1)
Memory Optimization (16.2)
Code Cleanup (16.3)
Test Optimization (16.4)
    ↓
Validation Testing
    ↓
Documentation (16.5, 16.6)
    ↓
Final Validation (16.7)
    ↓
PRODUCTION READY ✅
```

### Example Optimization Session
```bash
# 1. Profile CPU usage
python scripts/profile_cpu.py --service risk_engine --duration 60

# 2. Analyze hotspots
python scripts/analyze_profiles.py var/profiling/risk_engine/profile.stats

# 3. Profile memory
python scripts/profile_memory.py --service paper_trader --leak-detection

# 4. Run optimization suite
make optimize  # Runs all optimization tasks

# 5. Validate improvements
pytest tests/test_performance.py -v

# 6. Generate documentation
mkdocs build

# 7. Final validation
python scripts/production_validation.py --full
```

---

## Dependencies Summary

```
Phase 15 (Deployment Framework) ✅
    └─> Phase 16.0 (Performance Profiling) — CPU/memory profiling
            └─> 16.1 (Event Loop Optimization) — Latency reduction
                    └─> 16.2 (Memory Optimization) — Memory reduction
                            └─> 16.3 (Code Cleanup) — Dead code, duplicates
                                    └─> 16.4 (Test Suite Optimization) — Coverage, speed
                                            └─> 16.5 (API Documentation) — Auto-generated docs
                                                    └─> 16.6 (Operator Manual) — Comprehensive guide
                                                            └─> 16.7 (Final Validation) — Production sign-off
```

**Final Milestone:** Upon completion of Phase 16.7, the system is production-ready with enterprise-grade quality, performance, and documentation.

---

## Production Readiness Criteria

**System is production-ready when:**
1. ✅ All 16 phases complete
2. ✅ All tests passing (100% green)
3. ✅ Performance targets met (latency, throughput, memory)
4. ✅ Security validation passed
5. ✅ Documentation complete and validated
6. ✅ Operational procedures tested
7. ✅ Sign-off from all stakeholders

**Deployment Authorization:** Granted upon successful completion of Phase 16.7 Final Validation.

---
