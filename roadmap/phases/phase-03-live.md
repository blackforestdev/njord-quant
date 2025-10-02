## Phase 3 — Live Broker (Binance.US) ✅

### Phase 3.0 — Broker Interface ✅
**Status:** Complete
**Dependencies:** 2.1
**Task:** Define broker abstraction

**Interface:**
```python
class IBroker(ABC):
    def place(req: BrokerOrderReq) -> BrokerOrderAck
    def cancel(exchange_order_id: str) -> bool
    def fetch_open_orders(symbol: str | None) -> list[BrokerOrderUpdate]
    def fetch_balances() -> list[BalanceSnapshot]
```

**Contracts:**
- `BrokerOrderReq` (symbol, side, type, qty, limit_price, client_order_id)
- `BrokerOrderAck` (client_order_id, exchange_order_id, ts_ns)
- `BrokerOrderUpdate` (exchange_order_id, status, filled_qty, avg_price, ts_ns, raw)
- `BalanceSnapshot` (asset, free, locked, ts_ns)

**Files:**
- `core/broker.py` (80 LOC)
- `tests/test_broker_interface.py`

**Acceptance:** Interface typed, contracts immutable

---

### Phase 3.1 — Binance.US Adapter (Read-Only) ✅
**Status:** Complete
**Dependencies:** 3.0
**Task:** Implement `BinanceUSBroker` (read-only mode)

**Behavior:**
- `__init__(api_key, api_secret, read_only=True)`
- `place()` → raises `RuntimeError` if `read_only=True`
- `fetch_balances()` → via `ccxt.fetch_balance()`
- `fetch_open_orders()` → via `ccxt.fetch_open_orders()`
- `cancel()` → raises if `read_only=True`

**Files:**
- `apps/broker_binanceus/adapter.py` (100 LOC)
- `tests/test_binanceus_adapter_readonly.py`

**Acceptance:** Read methods work with mocked exchange, write methods blocked

---

### Phase 3.2 — Broker Reconnect & Backoff ✅
**Status:** Complete
**Dependencies:** 3.1
**Task:** Add retry logic for REST calls

**Helper Class:**
```python
class RestRetry:
    def __init__(self, config: RestRetryConfig, sleep_fn, logger): ...
    def call(self, func, *args, **kwargs) -> T: ...
```

**Behavior:**
- Retry on `NetworkError`, `429`, `418` (rate limit)
- Honor `Retry-After` header if present
- Exponential backoff: `base_delay * 2^(attempt-1)`, capped at `max_delay`
- Max attempts configurable

**Files:**
- `apps/broker_binanceus/backoff.py` (80 LOC)
- `tests/test_backoff_policy.py`

**Acceptance:** Respects `Retry-After`, backs off exponentially, eventually succeeds or exhausts

---

### Phase 3.3 — Broker User Stream (REST Polling) ✅
**Status:** Complete
**Dependencies:** 3.2
**Task:** Implement order update streaming

**API:**
```python
async with broker.start_user_stream() as stream:
    async for updates in stream:
        for update in updates: ...
```

**Behavior:**
- If `ccxt.pro` available: use WebSocket `watch_orders()`
- Fallback: REST polling every `poll_interval` seconds
- Emit diffs only (new orders, status changes, fills)
- Track open orders snapshot, compute delta
- Handle reconnects with exponential backoff

**Files:**
- `apps/broker_binanceus/adapter.py` (append ~100 LOC)
- `tests/test_user_stream_shim.py` (REST path)
- `tests/test_ws_reconnect_logic.py` (WebSocket path)

**Acceptance:** Updates streamed, reconnects handled gracefully

---

### Phase 3.4 — Broker Service (Dry-Run) ✅
**Status:** Complete
**Dependencies:** 3.3, 2.3
**Task:** Create `apps/broker_binanceus/main.py` (dry-run only)

**Behavior:**
- Subscribe to `orders.accepted` topic
- If `live_enabled=False` (dry-run):
  - Echo order to `broker.echo` topic (don't call broker)
  - Journal to `var/log/njord/broker.orders.ndjson`
- If `live_enabled=True` (not yet implemented):
  - Call `broker.place()` (Phase 3.5)
- Subscribe to `orders.cancel` topic → call `broker.cancel()`
- Stream user updates → publish to `broker.orders` topic
- Periodically publish balances to `broker.balances` topic
- Track inflight orders (add on place, remove on terminal status)

**CLI:**
```bash
python -m apps.broker_binanceus --config-root .
```

**Files:**
- `apps/broker_binanceus/main.py` (200 LOC)
- `tests/test_dry_run_echo.py`

**Acceptance:** Dry-run echoes requests, no live orders placed

---

### Phase 3.5 — Live Order Placement ✅
**Status:** Complete
**Dependencies:** 3.4
**Task:** Enable live order placement with safeguards

**Changes to `main.py`:**
- `live_enabled = config.app.env == "live" and os.getenv("NJORD_ENABLE_LIVE") == "1"`
- If `live_enabled`:
  - Call `broker.place(req)` → publish `BrokerOrderAck` to `broker.acks`
  - Add `client_order_id` to inflight set
- Else: dry-run (echo only)

**Hard Cap:**
- Before placing: compute `notional = qty * ref_price`
- If `notional > 10.0 USD` → deny with reason `live_micro_cap`
- Publish denial to `risk.decisions` topic

**Files:**
- `apps/broker_binanceus/main.py` (append ~50 LOC)
- `tests/test_live_toggle_guard.py` (env not set → dry-run)
- `tests/test_notional_cap_live.py` ($10 cap enforced)

**Acceptance:** Live placement only if both flags set, $10 cap enforced

---

### Phase 3.6 — Kill Switch Integration (Broker) ✅
**Status:** Complete
**Dependencies:** 3.5, 2.2
**Task:** Check kill switch before every live order

**Logic:**
```python
if file_tripped(path) or await redis_tripped(url, key):
    publish RiskDecision(allowed=false, reason="halted")
    return  # do not place order
```

**Files:**
- `apps/broker_binanceus/main.py` (append ~20 LOC)
- `tests/test_killswitch_blocks_live.py`

**Acceptance:** Kill switch trips → orders denied, logged with reason

---

### Phase 3.7 — Idempotent Order Placement ✅
**Status:** Complete
**Dependencies:** 3.6
**Task:** Handle duplicate `clientOrderId` gracefully

**Behavior:**
- On `place()` exception with "Duplicate clientOrderId":
  - Call `fetch_order(clientOrderId=X)`
  - If found: return existing `BrokerOrderAck`
  - If not found: raise `DuplicateClientOrderIdError`
- Custom exception class for clarity

**Files:**
- `apps/broker_binanceus/adapter.py` (append ~30 LOC)
- `tests/test_idempotent_place.py`

**Acceptance:** Duplicate placement returns existing ack, not error

---

### Phase 3.8 — Strategy Plugin Framework ✅
**Status:** Complete
**Dependencies:** 3.7, 2.4
**Task:** Implement hot-swappable strategy system

**Deliverables:**
1. `strategies/base.py` — Abstract base class
2. `strategies/context.py` — Injected state container
3. `strategies/registry.py` — Discovery + factory
4. `strategies/manager.py` — Lifecycle (load, reload, teardown)
5. `config/strategies.yaml` — Config schema
6. `strategies/samples/trendline_break.py` — Sample strategy
7. `strategies/samples/rsi_tema_bb.py` — Sample strategy
8. `tests/test_strategy_*.py` — Golden tests (deterministic signals)

**Detailed Task Breakdown:**

#### Task 3.8.1 — StrategyBase ABC ✅
**Files:** `strategies/base.py`

**API:**
```python
class StrategyBase(ABC):
    strategy_id: str

    @abstractmethod
    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        """Handle incoming event, yield zero or more intents."""
        pass
```

**Constraints:**
- Keep ≤50 LOC
- Must be importable without dependencies on Context yet
- Type-hinted with `from __future__ import annotations`

**Tests:**
- `tests/test_strategy_base.py` — Subclass implements `on_event()`

---

#### Task 3.8.2 — Strategy Context ✅
**Files:** `strategies/context.py`

**API:**
```python
@dataclass
class StrategyContext:
    """Injected state container for strategies."""
    strategy_id: str
    bus: BusProto  # for publishing intents
    positions: dict[str, PositionSnapshot]
    prices: dict[str, float]  # last trade prices
    config: dict[str, Any]  # strategy-specific params
```

**Constraints:**
- Immutable where possible (frozen dataclass)
- No business logic (pure data container)
- Keep ≤60 LOC

**Tests:**
- `tests/test_strategy_context.py` — Construct with valid data

---

#### Task 3.8.3 — StrategyRegistry ✅
**Files:** `strategies/registry.py`

**API:**
```python
class StrategyRegistry:
    def __init__(self): ...

    def register(self, strategy_class: type[StrategyBase]) -> None: ...

    def get(self, strategy_id: str) -> type[StrategyBase]: ...

    def discover(self, package: str = "strategies.samples") -> None:
        """Auto-discover strategies in package."""
        pass
```

**Behavior:**
- `discover()` imports all `.py` files in package
- Finds subclasses of `StrategyBase`
- Registers by `strategy_id` attribute

**Constraints:**
- Keep ≤80 LOC
- Handle import errors gracefully (log warning, skip)

**Tests:**
- `tests/test_strategy_registry.py` — Discover sample strategies

---

#### Task 3.8.4 — StrategyManager ✅
**Files:** `strategies/manager.py`

**API:**
```python
class StrategyManager:
    def __init__(self, registry: StrategyRegistry, bus: BusProto): ...

    async def load(self, config: dict[str, Any]) -> None:
        """Load strategies from config."""
        pass

    async def reload(self) -> None:
        """Hot-reload strategy instances."""
        pass

    async def run(self) -> None:
        """Main event loop: subscribe to events, dispatch to strategies."""
        pass
```

**Behavior:**
- Load strategies from `config/strategies.yaml`
- Instantiate with `StrategyContext`
- Subscribe to configured event topics
- On event: call `strategy.on_event()`, publish resulting `OrderIntent`s

**Constraints:**
- Keep ≤120 LOC
- Must support concurrent strategies
- Graceful degradation if strategy crashes (log + continue)

**Tests:**
- `tests/test_strategy_manager.py` — Load, dispatch event, verify intent published

---

#### Task 3.8.5 — Config Schema ✅
**Files:** `config/strategies.yaml`

**Schema:**
```yaml
strategies:
  - id: trendline_break_v1
    class: strategies.samples.trendline_break.TrendlineBreak
    enabled: true
    symbols: ["ATOM/USDT"]
    events: ["md.trades.*"]
    params:
      lookback_periods: 20
      breakout_threshold: 0.02

  - id: rsi_tema_bb_v1
    class: strategies.samples.rsi_tema_bb.RsiTemaBb
    enabled: false
    symbols: ["ATOM/USDT"]
    events: ["md.trades.*"]
    params:
      rsi_period: 14
      tema_period: 9
      bb_period: 20
      bb_std: 2.0
```

**Validation:**
- Each strategy must have unique `id`
- `class` must be importable
- `symbols` and `events` must be lists
- `params` dict passed to strategy via Context

---

#### Task 3.8.6 — Sample: Trendline Break ✅
**Files:** `strategies/samples/trendline_break.py`

**Logic:**
- Maintain rolling window of last N prices
- Compute linear regression trendline
- If current price breaks above trendline by threshold → buy signal
- If breaks below → sell signal

**Constraints:**
- Keep ≤100 LOC
- No external deps (use stdlib `statistics` for regression)
- Emit `OrderIntent` with `qty` from config

**Tests:**
- `tests/golden/trendline_break.jsonl` — Input prices, expected intents
- `tests/test_strategy_trendline_break.py` — Load golden, replay, compare

---

#### Task 3.8.7 — Sample: RSI + TEMA + Bollinger Bands ✅
**Files:** `strategies/samples/rsi_tema_bb.py`

**Logic:**
- RSI (Relative Strength Index) for momentum
- TEMA (Triple Exponential Moving Average) for trend
- Bollinger Bands for volatility
- Buy: RSI oversold + price below lower band + TEMA rising
- Sell: RSI overbought + price above upper band + TEMA falling

**Constraints:**
- Keep ≤100 LOC
- Use `ta-lib` bindings OR implement indicators manually
- Deterministic (fixed seed if using randomness)

**Tests:**
- `tests/golden/rsi_tema_bb.jsonl`
- `tests/test_strategy_rsi_tema_bb.py`

---

#### Task 3.8.8 — Strategy Runner Service ✅
**Files:** `apps/strategy_runner/main.py`

**Behavior:**
- Load `config/strategies.yaml`
- Instantiate `StrategyManager`
- Call `manager.run()` (blocks, subscribes to events)
- Publish `OrderIntent` to `strat.intent` topic

**CLI:**
```bash
python -m apps.strategy_runner --config ./config/base.yaml
```

**Tests:**
- `tests/test_strategy_runner_service.py` — E2E with in-memory bus

---

**Phase 3.8 Acceptance Criteria:**
- [x] All 8 tasks completed
- [x] `make fmt lint type test` green
- [x] Golden tests pass (deterministic signal generation)
- [x] Dry-run mode: strategies emit intents but no live orders
- [x] Config hot-reload works (manager can reload strategies)

---
