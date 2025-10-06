# Testing Guide for Code Agents

## Overview

This document provides code agents with explicit guidance on testing strategies for the Njord Quant framework. The framework uses a **two-tier testing strategy** to balance speed, security, and production-quality validation.

---

## Two-Tier Testing Strategy

### Tier 1: Unit Tests (Default, Always Run)

**Purpose:** Fast, deterministic tests with no external dependencies

**Characteristics:**
- Use `InMemoryBus` or mocks (never real Redis)
- No network I/O
- Deterministic (fixed seeds, no real sleeps)
- Fast (<30 seconds for entire suite)
- Required for ALL commits

**When to Use:**
- Default choice for all new tests
- Business logic validation
- Edge case handling
- Input validation
- Data transformations
- State management

**Example Pattern:**
```python
import pytest
from tests.utils import InMemoryBus
from core.contracts import OrderIntent

async def test_strategy_emits_intent_via_bus():
    """Unit test using InMemoryBus (no Redis)."""
    bus = InMemoryBus()
    strategy = MyStrategy(bus=bus)

    await strategy.on_event({"type": "signal", "action": "buy"})

    # Verify intent was published
    assert "strat.intent" in bus.published
    assert len(bus.published["strat.intent"]) == 1
    intent = bus.published["strat.intent"][0]
    assert intent["side"] == "buy"
```

---

### Tier 2: Integration Tests (When Critical)

**Purpose:** Validate real Redis pub/sub behavior when critical to acceptance criteria

**Characteristics:**
- Localhost Redis via Docker Compose ONLY
- Security: 127.0.0.1 binding (no external network)
- Gated with skip guards (env vars or availability checks)
- Isolated test topics (UUIDs to prevent cross-contamination)
- Required when acceptance criteria explicitly depend on Redis behavior

**When to Use:**
- Testing Redis pub/sub round-trip behavior
- Validating message serialization/deserialization
- Testing reconnection logic
- Verifying topic subscription patterns
- Testing Redis-specific features (TTL, persistence, etc.)

**When NOT to Use:**
- Business logic can be tested with `InMemoryBus`
- Data transformations (use unit tests)
- Input validation (use unit tests)
- General async behavior (use asyncio.Event or mocks)

**Example Pattern:**
```python
import asyncio
import os
import uuid
import pytest
from redis.asyncio import Redis
from core.bus import Bus

@pytest.mark.integration
async def test_redis_pubsub_round_trip():
    """Integration test with real Redis (gated)."""
    # Skip guard: Allow disabling via environment variable
    if os.getenv("REDIS_SKIP") == "1":
        pytest.skip("redis tests disabled")

    # Skip guard: Check Redis availability
    try:
        from redis.asyncio import Redis
    except ModuleNotFoundError:
        pytest.skip("redis library not installed")

    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = Redis.from_url(url)
    try:
        await asyncio.wait_for(client.ping(), timeout=1)
    except Exception as exc:
        pytest.skip(f"redis not available: {exc}")
    finally:
        await client.aclose()

    # Use isolated topic (UUID to prevent cross-contamination)
    bus = Bus(url)
    topic = f"test.integration.{uuid.uuid4().hex}"
    received = []

    async def consume_one():
        async for item in bus.subscribe(topic):
            received.append(item)
            break

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0.05)  # Allow subscription to establish
    await bus.publish_json(topic, {"test": "data", "value": 42})

    await asyncio.wait_for(task, timeout=5)
    assert received == [{"test": "data", "value": 42}]

    await bus.close()
```

---

## Running Tests

### Unit Tests (Default)

```bash
# Format, lint, type-check, and run unit tests
make fmt && make lint && make type && make test

# Run specific unit test file
PYTHONPATH=. pytest tests/test_mymodule.py -v

# Run with coverage
PYTHONPATH=. pytest tests/ --cov=core --cov=execution
```

### Integration Tests (When Required)

```bash
# Start isolated test Redis (localhost only, 127.0.0.1 binding)
docker-compose -f docker-compose.test.yml up -d redis

# Wait for Redis to be ready
docker-compose -f docker-compose.test.yml exec redis redis-cli ping

# Run integration tests only
PYTHONPATH=. pytest -v -m integration

# Run specific integration test
PYTHONPATH=. pytest tests/test_bus_pubsub.py -v

# Cleanup (always run after integration tests)
docker-compose -f docker-compose.test.yml down
```

### Full Test Suite (Unit + Integration)

```bash
# Start Redis
docker-compose -f docker-compose.test.yml up -d redis

# Run all tests (unit + integration)
make fmt && make lint && make type && make test
PYTHONPATH=. pytest -v -m integration

# Cleanup
docker-compose -f docker-compose.test.yml down
```

---

## Security Guardrails

### Critical Security Rules for Integration Tests

1. **Localhost Binding Only**
   - Docker Compose MUST bind Redis to 127.0.0.1:6379 (not 0.0.0.0)
   - Verify in `docker-compose.test.yml`:
     ```yaml
     ports:
       - "127.0.0.1:6379:6379"  # ✅ CORRECT
       - "6379:6379"             # ❌ PROHIBITED (binds to 0.0.0.0)
     ```

2. **No External Network**
   - Integration tests connect to `redis://127.0.0.1:6379/0` ONLY
   - Never connect to external Redis instances
   - Never use production credentials

3. **Isolated Test Topics**
   - Use UUIDs in topic names: `f"test.{uuid.uuid4().hex}"`
   - Prevents cross-contamination between test runs
   - Ensures determinism

4. **Skip Guards Required**
   - All integration tests MUST include skip guards
   - Allow disabling via `REDIS_SKIP=1` environment variable
   - Check Redis availability before running

5. **Resource Limits**
   - Docker Compose config includes `maxmemory 256mb`
   - Prevents resource exhaustion
   - Ephemeral containers (no data persistence)

---

## Testing Patterns for Common Scenarios

### Pattern 1: Testing Strategy Logic (Unit Test)

```python
from tests.utils import InMemoryBus

async def test_strategy_generates_buy_signal():
    """Test business logic without real Redis."""
    bus = InMemoryBus()
    strategy = TrendlineBreakStrategy(bus=bus, symbol="BTC/USDT")

    # Inject market data
    await strategy.on_event({
        "type": "ticker",
        "symbol": "BTC/USDT",
        "last": 50000.0
    })

    # Verify strategy emitted OrderIntent
    assert "strat.intent" in bus.published
    intent = bus.published["strat.intent"][0]
    assert intent["side"] == "buy"
```

### Pattern 2: Testing Bus Round-Trip (Integration Test)

```python
import uuid
import pytest

@pytest.mark.integration
async def test_bus_serializes_complex_payload():
    """Test Redis handles complex JSON payloads."""
    if os.getenv("REDIS_SKIP") == "1":
        pytest.skip("redis tests disabled")

    # ... (skip guards as shown above) ...

    bus = Bus("redis://127.0.0.1:6379/0")
    topic = f"test.{uuid.uuid4().hex}"

    complex_payload = {
        "nested": {"data": [1, 2, 3]},
        "float": 123.456,
        "null": None
    }

    received = []
    async def consume():
        async for msg in bus.subscribe(topic):
            received.append(msg)
            break

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    await bus.publish_json(topic, complex_payload)
    await asyncio.wait_for(task, timeout=5)

    assert received[0] == complex_payload
    await bus.close()
```

### Pattern 3: Testing Execution Algorithm (Unit Test)

```python
from execution.twap import TWAPExecutor
from tests.utils import InMemoryBus

async def test_twap_slices_order_correctly():
    """Test TWAP slicing logic without Redis."""
    bus = InMemoryBus()
    executor = TWAPExecutor(strategy_id="test", bus=bus)

    algo_params = {
        "total_quantity": 100.0,
        "num_slices": 4,
        "interval_sec": 60
    }

    intents = await executor.plan_execution(algo_params)

    # Verify slicing
    assert len(intents) == 4
    assert all(i.quantity == 25.0 for i in intents)
    assert intents[0].meta["slice_id"] == 0
```

---

## Acceptance Criteria for Redis-Dependent Modules

When implementing a module that uses Redis pub/sub, acceptance criteria must include BOTH unit and integration tests:

### Required Acceptance Items

✅ **Unit tests use `InMemoryBus` (no Redis dependency)**
- Validates business logic, data transformations, edge cases
- Fast, deterministic, no network I/O

✅ **Integration test verifies Redis pub/sub round-trip (gated, localhost only)**
- Validates serialization/deserialization
- Tests topic subscription patterns
- Verifies message delivery

✅ **Test includes skip guards**
- `if os.getenv("REDIS_SKIP") == "1": pytest.skip()`
- Availability check with timeout
- Graceful degradation if Redis unavailable

✅ **Docker Compose config binds to 127.0.0.1 only**
- Verified in `docker-compose.test.yml`
- No external network exposure

### Example Acceptance Criteria (from roadmap phase spec)

```markdown
**Acceptance:**
- Unit tests use InMemoryBus for strategy logic (no Redis)
- Integration test verifies strategy → risk engine pub/sub flow
- Test includes skip guard: `REDIS_SKIP=1` or availability check
- Test uses isolated topic: `f"test.{uuid.uuid4().hex}"`
- Docker Compose verified to bind 127.0.0.1 only
- make fmt lint type test green
- Audit must PASS (zero High/Medium findings)
```

---

## Code Agent Implementation Checklist

When implementing a new module with Redis dependencies:

### Phase 1: Implementation
- [ ] Use `BusProto` protocol for dependency injection
- [ ] Design for testability (accept `bus` parameter)
- [ ] Never hardcode Redis URLs (use config or test fixtures)

### Phase 2: Unit Tests
- [ ] Create unit tests using `InMemoryBus`
- [ ] Test all business logic paths
- [ ] Validate edge cases and error handling
- [ ] Ensure determinism (fixed seeds, no real sleeps)

### Phase 3: Integration Tests (If Required)
- [ ] Mark with `@pytest.mark.integration`
- [ ] Add skip guards (`REDIS_SKIP=1` check)
- [ ] Add availability check (Redis ping with timeout)
- [ ] Use isolated topics (`uuid.uuid4().hex`)
- [ ] Test Redis-specific behavior ONLY (not business logic)
- [ ] Clean up connections (`await bus.close()`)

### Phase 4: Verification
- [ ] Run unit tests: `make fmt lint type test` (all green)
- [ ] Start Redis: `docker-compose -f docker-compose.test.yml up -d redis`
- [ ] Run integration tests: `pytest -v -m integration` (all green)
- [ ] Cleanup: `docker-compose -f docker-compose.test.yml down`

### Phase 5: Audit
- [ ] Run audit per AUDIT.md
- [ ] Verify security: 127.0.0.1 binding only
- [ ] Confirm skip guards present
- [ ] Zero High/Medium findings

---

## Troubleshooting

### "Redis connection refused" in Integration Tests

**Solution:**
```bash
# Check if Redis is running
docker-compose -f docker-compose.test.yml ps

# Start Redis if not running
docker-compose -f docker-compose.test.yml up -d redis

# Verify connectivity
docker-compose -f docker-compose.test.yml exec redis redis-cli ping
# Expected output: PONG
```

### Integration Tests Hang or Timeout

**Common Causes:**
1. Subscription established after publish (add `await asyncio.sleep(0.05)`)
2. Missing `break` in subscription loop (infinite loop)
3. Topic name mismatch (typo in topic string)
4. Redis not ready (wait for healthcheck)

**Debug Pattern:**
```python
# Add timeout to subscription
async with asyncio.timeout(5):  # Python 3.11+
    async for msg in bus.subscribe(topic):
        received.append(msg)
        break  # Don't forget this!
```

### Tests Pass Locally but Fail in CI

**Checklist:**
1. Verify `docker-compose.test.yml` in repository
2. Ensure CI config starts Redis before tests
3. Check network isolation (some CI runners restrict localhost)
4. Verify skip guards are present (tests should skip gracefully)

---

## Best Practices Summary

### DO ✅
- Use `InMemoryBus` for unit tests (default choice)
- Use real Redis ONLY when testing Redis-specific behavior
- Include skip guards for all integration tests
- Use isolated topics with UUIDs
- Bind Docker Compose to 127.0.0.1 only
- Clean up connections and containers

### DON'T ❌
- Use real Redis for business logic tests
- Skip unit tests in favor of integration tests
- Hardcode Redis URLs or topics
- Share test topics between tests
- Bind to 0.0.0.0 in Docker Compose
- Leave Redis containers running after tests

---

## References

- **AGENTS.md** — Strategic testing policies and verification protocol
- **AUDIT.md** — Test coverage audit procedures
- **docker-compose.test.yml** — Isolated test Redis configuration
- **tests/test_bus_pubsub.py** — Reference integration test pattern
- **tests/utils.py** — `InMemoryBus` implementation

---

**Last Updated:** 2025-10-06
**Maintained By:** Njord Trust
**License:** Proprietary
