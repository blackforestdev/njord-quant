## Phase 2 — Risk Engine MVP & Paper OMS ✅

### Phase 2.1 — Phase 2 Contracts ✅
**Status:** Complete
**Dependencies:** 1.1
**Task:** Extend contracts for risk/trading

**New Contracts:**
- `OrderIntent` (strategy_id, symbol, side, type, qty, limit_price)
- `RiskDecision` (intent_id, allowed, reason, caps)
- `OrderEvent` (intent_id, venue, symbol, side, type, qty, ts_accepted_ns)
- `FillEvent` (order_id, symbol, side, qty, price, fee, ts_fill_ns)
- `PositionSnapshot` (symbol, qty, avg_price, realized_pnl, ts_ns)

**Files:**
- `core/contracts.py` (append ~80 LOC)
- `tests/test_contracts_phase2.py`

**Acceptance:** All contracts frozen, typed, serializable

---

### Phase 2.2 — Kill Switch ✅
**Status:** Complete
**Dependencies:** 0.2
**Task:** Implement kill switch checks

**API:**
```python
# File-based
kill_switch.file_tripped(path: str) -> bool
kill_switch.trip_file(path: str) -> None
kill_switch.clear_file(path: str) -> None

# Redis-based
await kill_switch.redis_tripped(url: str, key: str) -> bool
```

**Files:**
- `core/kill_switch.py` (40 LOC)
- `scripts/njord_kill.py` (CLI helper)
- `tests/test_kill_switch_file.py`
- `tests/test_kill_switch_redis.py` (fakeredis ok)

**Acceptance:** File exists → tripped, Redis key="1" → tripped

---

### Phase 2.3 — Risk Engine (MVP) Service ✅
**Status:** Complete
**Dependencies:** 2.1, 2.2, 1.2
**Task:** Create `apps/risk_engine/main.py`

**Behavior:**
- Subscribe to `OrderIntent` on Redis topic `strat.intent`
- Enforce caps from `Config.risk`:
  - `per_order_usd_cap`: if `qty * ref_price > cap` → deny
  - `daily_loss_usd_cap`: placeholder (read from Redis `njord:pnl:day`, default 0)
  - `orders_per_min_cap`: token bucket (Redis or in-memory)
  - Kill-switch: if `file_tripped()` or `redis_tripped()` → deny with reason "halted"
- `ref_price` source: subscribe to `md.trades.*`, maintain last-price cache per symbol; fallback to `intent.limit_price` if unknown
- **If allowed:** publish `RiskDecision(allowed=true)` to `risk.decisions` + forward `OrderEvent` to `orders.accepted`
- **If denied:** publish `RiskDecision(allowed=false, reason=X)` to `risk.decisions`; do NOT forward
- JSON logging to `var/log/njord/app.ndjson`
- Journal decisions to `var/log/njord/risk.decisions.ndjson`

**Helper Class:**
```python
class RateLimiter:
    def __init__(self, symbol: str, cap_per_min: int): ...
    async def acquire(self) -> bool: ...
```

**Files:**
- `apps/risk_engine/main.py` (150 LOC)
- `tests/test_risk_per_order_cap.py`
- `tests/test_risk_killswitch.py`
- `tests/test_risk_rate_limit.py`

**Acceptance:** `make fmt lint type test` green, skip redis tests if unavailable

---

### Phase 2.4 — Paper Trader Service ✅
**Status:** Complete
**Dependencies:** 2.3
**Task:** Create `apps/paper_trader/main.py`

**Behavior:**
- Subscribe to `orders.accepted` topic
- Simulate fills:
  - Market orders: fill at `last_trade_price[symbol]` or `limit_price` fallback
  - Limit orders: fill if `last_price` crosses limit (buy: last ≤ limit, sell: last ≥ limit)
- Track positions per symbol:
  - FIFO accounting for PnL calculation
  - Maintain `qty`, `avg_price`, `realized_pnl`
- Publish `FillEvent` to `fills.new`
- Publish `PositionSnapshot` to `positions.snapshot`
- Journal fills to `var/log/njord/fills.{symbol}.ndjson`
- Journal positions to `var/log/njord/positions.{symbol}.ndjson`

**Files:**
- `apps/paper_trader/main.py` (180 LOC)
- `tests/test_paper_fill_market.py`
- `tests/test_paper_fill_limit.py`
- `tests/test_paper_position_math.py` (long, short, reversals)

**Acceptance:** Position math correct (compare against manual calculation), fills deterministic

---

### Phase 2.5 — Phase 2 E2E Test ✅
**Status:** Complete
**Dependencies:** 2.3, 2.4
**Task:** Integration test across risk + paper

**Scenario:**
1. Start risk engine + paper trader (in-memory bus)
2. Publish trade event (set last price)
3. Publish `OrderIntent`
4. Verify `RiskDecision` allowed
5. Verify `OrderEvent` forwarded
6. Verify `FillEvent` published
7. Verify `PositionSnapshot` updated

**Files:**
- `tests/test_phase2_e2e.py` (80 LOC, uses `InMemoryBus` test helper)

**Acceptance:** End-to-end flow deterministic, completes in <1s

---
