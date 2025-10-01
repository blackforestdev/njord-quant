# Njord Quant — Development Roadmap

**Purpose:** Detailed task-level instructions for each phase/sub-phase.
**Audience:** AI coding agents (Codex, Claude Code), human developers.
**Status Tracking:** ✅ Complete | 🚧 In Progress | 📋 Planned

---

## How to Use This Document

### For AI Agents
1. Locate current phase (check `[STATUS]` markers)
2. Read **Dependencies** section to ensure prerequisites are met
3. Follow **Task** instructions exactly
4. Verify against **Acceptance Criteria**
5. Update status marker upon completion

### For Humans
- Track overall progress via phase completion markers
- Use as reference for architectural decisions
- Cross-reference with `AGENTS.md` for SOPs

---

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

## Phase 1 — Event Bus & Market Data Ingest ✅

### Phase 1.0 — Redis Pub/Sub Bus ✅
**Status:** Complete
**Dependencies:** 0.4
**Task:** Async Redis wrapper for pub/sub

**API:**
```python
bus = Bus(redis_url)
await bus.publish_json(topic, payload)
async for msg in bus.subscribe(topic): ...
```

**Files:**
- `core/bus.py` (60 LOC)
- `tests/test_bus_pubsub.py` (requires Redis or fakeredis)

**Acceptance:** Round-trip message delivery verified

---

### Phase 1.1 — Market Data Contracts ✅
**Status:** Complete
**Dependencies:** 1.0
**Task:** Define event contracts in `core/contracts.py`

**Contracts:**
- `TradeEvent` (symbol, price, qty, side, ts)
- `BookEvent` (symbol, bids, asks, checksum)
- `TickerEvent` (symbol, last, bid, ask, volume)

**Files:**
- `core/contracts.py` (60 LOC, frozen dataclasses)
- `tests/test_contracts_basic.py`

**Acceptance:** Immutable, type-checked, serializable to dict

---

### Phase 1.2 — Market Data Ingest Daemon ✅
**Status:** Complete
**Dependencies:** 1.1
**Task:** Create `apps/md_ingest/main.py` using CCXT Pro

**Behavior:**
- `watch_trades(symbol)` → publish to `md.trades.{symbol}`
- Deduplicate by trade ID (rolling window of 512 IDs)
- Journal to `var/log/njord/md.trades.{symbol}.ndjson`
- Reconnect with exponential backoff on disconnect

**CLI:**
```bash
python -m apps.md_ingest --symbol ATOM/USDT --venue binanceus
```

**Files:**
- `apps/md_ingest/main.py` (120 LOC)
- `tests/test_md_ingest_dedupe.py`

**Acceptance:** Trades published without duplicates, journal replay matches

---

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

### Phase 3.8 — Strategy Plugin Framework 🚧
**Status:** In Progress
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

#### Task 3.8.6 — Sample: Trendline Break 📋
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

#### Task 3.8.7 — Sample: RSI + TEMA + Bollinger Bands 📋
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

#### Task 3.8.8 — Strategy Runner Service 📋
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
- [ ] All 8 tasks completed
- [ ] `make fmt lint type test` green
- [ ] Golden tests pass (deterministic signal generation)
- [ ] Dry-run mode: strategies emit intents but no live orders
- [ ] Config hot-reload works (manager can reload strategies)

---

## Phase 4 — Market Data Storage 📋

### Phase 4.1 — OHLCV Aggregator 📋
**Task:** Subscribe to trades, compute 1m/5m/1h bars, persist to disk

### Phase 4.2 — Compression & Rotation 📋
**Task:** Gzip old journals, rotate by date/size

### Phase 4.3 — Replay Interface 📋
**Task:** API to replay historical data for backtesting

---

## Phase 5 — Backtester 📋

### Phase 5.1 — Event Replay Engine 📋
**Task:** Deterministic replay from journals

### Phase 5.2 — Equity Curve Calculation 📋
**Task:** Track portfolio value over time

### Phase 5.3 — Golden Equity Tests 📋
**Task:** Snapshot expected curves, compare

---

## Phases 6-16 (Outline Only)

**Phase 6:** Portfolio Allocator (capital allocation across strategies)
**Phase 7:** Research API (pandas/pyarrow interface)
**Phase 8:** Execution Layer (smart routing, slippage)
**Phase 9:** Metrics & Telemetry (Prometheus, Grafana)
**Phase 10:** Live Trade Controller (unified CLI)
**Phase 11:** Monitoring & Alerts (Slack/Email)
**Phase 12:** Compliance & Audit (immutable logs)
**Phase 13:** Advanced Strategies (ML features, ensembles)
**Phase 14:** Simulation Harness (stress tests)
**Phase 15:** Deployment Framework (systemd, Ansible)
**Phase 16:** Optimization Pass (profiling, cleanup, docs)

---

## Appendix: Task Template

Copy this for new tasks:

```markdown
### Phase X.Y — <Task Name> <Status Emoji>
**Status:** 📋 Planned | 🚧 In Progress | ✅ Complete
**Dependencies:** X.Y-1, ...
**Task:** <One-sentence summary>

**Behavior:**
- <Bullet point 1>
- <Bullet point 2>

**Files:**
- `path/to/file.py` (estimated LOC)
- `tests/test_file.py`

**Acceptance:** <Explicit pass/fail criteria>
```

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

**Last Updated:** 2025-09-30
**Maintained By:** Njord Trust
