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

## Phase 4 — Market Data Storage ✅

### Phase 4.1 — OHLCV Bar Dataclass ✅
**Status:** Complete
**Dependencies:** 1.2 (Market Data Ingest)
**Task:** Define OHLCV bar contract

**API:**
```python
@dataclass(frozen=True)
class OHLCVBar:
    symbol: str
    timeframe: str  # "1m", "5m", "1h"
    ts_open: int    # epoch ns
    ts_close: int
    open: float
    high: float
    low: float
    close: float
    volume: float
```

**Files:**
- core/contracts.py (append ~30 LOC)
- tests/test_ohlcv_contract.py

**Acceptance:**
- Immutable dataclass (frozen=True)
- All fields typed correctly
- Serializable to/from dict
- Test verifies immutability
- `make fmt lint type test` green

---

### Phase 4.2 — Trade-to-OHLCV Aggregator ✅
**Status:** Complete
**Dependencies:** 4.1 (OHLCV Bar Dataclass)
**Task:** Aggregate trades into OHLCV bars

**Behavior:**
- Subscribe to md.trades.{symbol} topic
- Buffer trades in memory per timeframe
- Emit complete bars when time window closes
- Publish to md.ohlcv.{timeframe}.{symbol} topic
- Handle gaps (no trades) by repeating last close

**Files:**
- apps/ohlcv_aggregator/main.py (150 LOC)
- tests/test_ohlcv_aggregator.py

**Acceptance:**
- Deterministic bar creation verified
- Gap handling tested (no trades → repeat close)
- Edge cases covered (single trade, midnight boundary)
- Bars published to correct Redis topics
- `make fmt lint type test` green

---

### Phase 4.3 — Multi-Timeframe Support ✅
**Status:** Complete
**Dependencies:** 4.2
**Task:** Support multiple concurrent timeframes

**Behavior:**
- Single aggregator instance handles ["1m", "5m", "15m", "1h"]
- Each timeframe has independent buffer
- 5m/15m/1h bars derived from 1m (not raw trades)
- Aligned to wall-clock boundaries (e.g., 1h bar at :00)

**Files:**
- apps/ohlcv_aggregator/main.py (append ~80 LOC)
- tests/test_multi_timeframe.py

**Acceptance:**
- All timeframes align to wall-clock boundaries
- No drift detected across 24h simulation
- 5m/15m/1h bars correctly derived from 1m
- Test includes concurrent multi-timeframe aggregation
- `make fmt lint type test` green

---

### Phase 4.4 — OHLCV Persistence ✅
**Status:** Complete
**Dependencies:** 4.3
**Task:** Journal OHLCV bars to disk

**Behavior:**
- Write bars to var/log/njord/ohlcv.{timeframe}.{symbol}.ndjson
- One line per bar (JSON serialized)
- Flush after each bar
- Separate journal per symbol+timeframe

**Files:**
- apps/ohlcv_aggregator/main.py (append ~40 LOC)
- tests/test_ohlcv_persistence.py

**Acceptance:**
- Journals written to correct paths
- NDJSON format parseable
- Replay matches original bars exactly
- Flush after each bar verified
- `make fmt lint type test` green

---

### Phase 4.5 — Gzip Compression Service ✅
**Status:** Complete
**Dependencies:** 4.4
**Task:** Compress old OHLCV journals

**Behavior:**
- Scan var/log/njord/ for .ndjson files older than 24h
- Compress with gzip (level 6)
- Rename: file.ndjson → file.YYYYMMDD.ndjson.gz
- Remove original uncompressed file
- Run as cron job or systemd timer

**Files:**
- scripts/compress_journals.py (80 LOC)
- tests/test_compression.py

**Acceptance:**
- [x] Compressed files readable with gzip
- [x] Original content preserved bit-for-bit
- [x] Files older than 24h correctly identified
- [x] Compression ratio >50% on test data
- [x] `make fmt lint type test` green

---

### Phase 4.6 — Rotation Policy ✅
**Status:** Complete
**Dependencies:** 4.5
**Task:** Rotate journals by date/size

**Behavior:**
- Daily rotation: start new journal at midnight UTC
- Size rotation: if journal exceeds 100MB, rotate immediately
- Naming: ohlcv.1m.ATOMUSDT.20250930.ndjson
- Compress rotated files automatically

**Files:**
- apps/ohlcv_aggregator/rotator.py (60 LOC)
- tests/test_rotation.py

**Acceptance:**
- [x] Daily rotation triggers at midnight UTC
- [x] Size rotation triggers at 100MB threshold
- [x] No data loss during rotation
- [x] Naming convention followed exactly
- [x] `make fmt lint type test` green

---

### Phase 4.7 — Journal Reader API ✅
**Status:** Complete
**Dependencies:** 4.6
**Task:** Read OHLCV journals for replay
**API:**
```python
class JournalReader:
    def __init__(self, path: Path): ...

    def read_bars(
        self,
        symbol: str,
        timeframe: str,
        start: int,  # epoch ns
        end: int
    ) -> Iterator[OHLCVBar]: ...
```

**Behavior:**
- Handle both compressed (.gz) and uncompressed files
- Filter by time range
- Parse NDJSON lines into OHLCVBar objects
- Raise error on malformed lines

**Files:**
- core/journal_reader.py (100 LOC)
- tests/test_journal_reader.py

**Acceptance:**
- [x] Reads both .ndjson and .ndjson.gz files
- [x] Time range filtering accurate to nanosecond
- [x] Malformed lines raise clear errors
- [x] Iterator pattern works for large files
- [x] `make fmt lint type test` green

---

### Phase 4.8 — Event Stream Replay ✅
**Status:** Complete
**Dependencies:** 4.7
**Task:** Replay historical OHLCV bars
**Behavior:**
- Load bars from journals
- Emit to Redis bus at controlled speed
- Publish to same topics as live aggregator
- Support speed multiplier (1x, 10x, 100x, max)
- Replay multiple symbols concurrently

**Files:**
- apps/replay_engine/main.py (120 LOC)
- tests/test_replay_engine.py

**Acceptance:**
- [x] Replay produces identical event sequences
- [x] Speed control verified (1x, 10x, 100x)
- [x] Multiple symbols replay concurrently without interference
- [x] Deterministic across multiple runs
- [x] `make fmt lint type test` green

---

### Phase 4.9 — Replay CLI ✅
**Status:** Complete
**Dependencies:** 4.8
**Task:** Command-line interface for replay

**CLI:**
```bash
python -m apps.replay_engine \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2025-09-01T00:00:00Z \
    --end 2025-09-30T23:59:59Z \
    --speed 10x
```

**Files:**
- apps/replay_engine/main.py (append ~50 LOC)
- tests/test_replay_cli.py

**Acceptance:**
- [x] All CLI arguments parsed correctly
- [x] Date/time parsing handles ISO 8601
- [x] Invalid args produce helpful error messages
- [x] CLI help text complete and accurate
- [x] `make fmt lint type test` green

---

**Phase 4 Acceptance Criteria:**
- [x] All 9 tasks completed
- [x] make fmt lint type test green
- [x] OHLCV bars persist and compress correctly
- [x] Replay deterministic across all timeframes
- [x] Journals rotate without data loss

---

## Phase 5 — Backtester ✅

### Phase 5.1 — Backtest Contracts ✅
**Status:** Complete
**Dependencies:** 4.7 (Journal Reader API)
**Task:** Define backtest-specific contracts

**API:**
```python
@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    strategy_id: str
    start_ts: int  # epoch ns
    end_ts: int
    initial_capital: float
    commission_rate: float  # e.g., 0.001 = 0.1%
    slippage_bps: float  # basis points

@dataclass(frozen=True)
class BacktestResult:
    strategy_id: str
    symbol: str
    start_ts: int
    end_ts: int
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    num_trades: int
    win_rate: float
    profit_factor: float
    equity_curve: list[tuple[int, float]]  # (ts_ns, capital)
```

**Files:**
- `backtest/contracts.py` (60 LOC)
- `tests/test_backtest_contracts.py`

**Acceptance:**
- [x] All contracts immutable and typed
- [x] Equity curve serializable to JSON
- [x] `make fmt lint type test` green

---

### Phase 5.2 — Backtest Engine Core ✅
**Status:** Complete
**Dependencies:** 5.1
**Task:** Implement deterministic event replay engine

**Behavior:**
- Load OHLCV bars from journals via `JournalReader`
- Replay bars in chronological order
- Inject bars into strategy via `on_event()`
- Collect `OrderIntent` emissions
- Pass intents through simulated risk engine
- Generate fills based on bar data (no slippage yet)
- Track position and capital changes
- Emit equity curve point after each bar

**Files:**
- `backtest/engine.py` (200 LOC)
- `tests/test_backtest_engine.py`

**Acceptance:**
- [x] Deterministic: same input → same output
- [x] Replay handles multi-day periods
- [x] Position tracking accurate
- [x] Test includes buy-hold baseline
- [x] `make fmt lint type test` green

---

### Phase 5.3 — Fill Simulation ✅
**Status:** Complete
**Dependencies:** 5.2
**Task:** Simulate order fills with realistic assumptions

**Behavior:**
- Market orders: fill at bar close price
- Limit orders:
  - Buy: fill if bar low ≤ limit price, fill at limit
  - Sell: fill if bar high ≥ limit price, fill at limit
  - Partial fills not supported (simplification)
- Apply commission per fill: `qty * price * commission_rate`
- Apply slippage: market orders use `price * (1 + slippage_bps/10000)`

**Files:**
- `backtest/fill_simulator.py` (100 LOC)
- `tests/test_fill_simulator.py`

**Acceptance:**
- Limit order logic validated against edge cases
- Commission correctly deducted from capital
- Slippage applied asymmetrically (buy: +slippage, sell: -slippage)
- Test includes zero-commission baseline
- `make fmt lint type test` green

---

### Phase 5.4 — Equity Curve Calculation ✅
**Status:** Complete
**Dependencies:** 5.3
**Task:** Track portfolio value over time

**Behavior:**
- After each bar, compute:
  - `cash` (available capital)
  - `position_value` = `qty * current_price`
  - `equity` = `cash + position_value`
- Store `(ts_ns, equity)` tuples
- Handle multiple positions (future): sum all position values
- Emit equity curve as part of `BacktestResult`

**Files:**
- `backtest/equity_tracker.py` (80 LOC)
- `tests/test_equity_tracker.py`

**Acceptance:**
- Equity curve monotonically increasing for profitable strategies
- Handles zero position (100% cash)
- Handles fully invested (0% cash)
- Test includes drawdown scenarios
- `make fmt lint type test` green

---

### Phase 5.5 — Performance Metrics ✅
**Status:** Complete
**Dependencies:** 5.4
**Task:** Calculate backtest performance statistics

**Metrics:**
```python
def calculate_metrics(equity_curve: list[tuple[int, float]]) -> dict[str, float]:
    return {
        "total_return_pct": ...,
        "sharpe_ratio": ...,       # Annualized
        "max_drawdown_pct": ...,
        "max_drawdown_duration_days": ...,
        "volatility_annual_pct": ...,
        "calmar_ratio": ...,       # Return / Max DD
        "win_rate": ...,
        "profit_factor": ...,      # Gross profit / Gross loss
        "avg_win": ...,
        "avg_loss": ...,
        "largest_win": ...,
        "largest_loss": ...,
    }
```

**Files:**
- `backtest/metrics.py` (150 LOC)
- `tests/test_backtest_metrics.py`

**Acceptance:**
- Sharpe ratio matches manual calculation
- Max drawdown correctly identified
- Handles edge cases (no trades, all wins, all losses)
- Test includes golden metrics for known equity curves
- `make fmt lint type test` green

---

### Phase 5.6 — Backtest Runner CLI ✅
**Status:** Complete
**Dependencies:** 5.5
**Task:** Command-line interface for running backtests

**CLI:**
```bash
python -m backtest.runner \
    --strategy trendline_break_v1 \
    --symbol ATOM/USDT \
    --start 2025-01-01 \
    --end 2025-09-30 \
    --capital 10000 \
    --commission 0.001 \
    --slippage 5
```

**Output:**
```
Backtest Results: trendline_break_v1 on ATOM/USDT
═══════════════════════════════════════════════════
Period:         2025-01-01 → 2025-09-30 (273 days)
Initial:        $10,000.00
Final:          $12,450.32
Total Return:   +24.50%
Sharpe Ratio:   1.85
Max Drawdown:   -8.23%
Trades:         47 (win rate: 63.8%)
Profit Factor:  2.14

Equity curve saved to: var/backtest/equity_trendline_break_v1_ATOMUSDT.ndjson
```

**Files:**
- `backtest/runner.py` (120 LOC)
- `tests/test_backtest_runner.py`

**Acceptance:**
- CLI parses all arguments correctly
- Results printed in human-readable format
- Equity curve saved to file
- Exit code 0 on success, 1 on error
- `make fmt lint type test` green

---

### Phase 5.7 — Golden Backtest Tests ✅
**Status:** Complete
**Dependencies:** 5.6
**Task:** Snapshot-test known backtest results

**Behavior:**
- Define "golden" backtest scenarios:
  - `golden_buy_hold.yaml`: Buy at start, hold until end
  - `golden_ma_cross.yaml`: Simple moving average crossover
  - `golden_trendline.yaml`: Trendline break strategy
- Run each scenario, capture metrics
- Store as `tests/golden/backtest_*.json`
- On each test run, verify metrics match within 0.01% tolerance

**Files:**
- `tests/golden/` (3 JSON files)
- `tests/test_golden_backtests.py` (100 LOC)

**Acceptance:**
- Golden tests pass on fresh clone
- Metrics deterministic across runs
- Tolerance accounts for floating-point precision
- Test fails if metrics deviate
- `make fmt lint type test` green

---

### Phase 5.8 — Parameter Sweep Harness ✅
**Status:** Complete
**Dependencies:** 5.7
**Task:** Run backtests across parameter ranges

**API:**
```python
class ParameterSweep:
    def __init__(self, strategy_id: str, symbol: str): ...

    def add_param_range(self, name: str, values: list[Any]) -> None:
        """Add parameter to sweep (e.g., 'lookback_periods', [10, 20, 30])"""

    async def run(self) -> pd.DataFrame:
        """Run all combinations, return DataFrame of results"""
```

**Behavior:**
- Generate all combinations of parameter ranges
- Run backtest for each combination
- Collect metrics in DataFrame
- Sort by Sharpe ratio (or user-specified metric)
- Save results to `var/backtest/sweep_results.csv`

**Example:**
```python
sweep = ParameterSweep("trendline_break_v1", "ATOM/USDT")
sweep.add_param_range("lookback_periods", [10, 20, 30])
sweep.add_param_range("breakout_threshold", [0.01, 0.02, 0.03])
results = await sweep.run()  # 9 combinations
```

**Files:**
- `backtest/param_sweep.py` (150 LOC)
- `tests/test_param_sweep.py`

**Acceptance:**
- All combinations executed
- Results sortable by any metric
- CSV output parseable by pandas
- Concurrent execution (optional)
- `make fmt lint type test` green

---

### Phase 5.9 — Backtest Report Generator ✅
**Status:** Complete
**Dependencies:** 5.8
**Task:** Generate visual HTML reports

**Features:**
- Equity curve chart (plotly or matplotlib)
- Drawdown chart
- Monthly returns heatmap
- Trade distribution histogram
- Performance metrics table
- Save as self-contained HTML

**Files:**
- `backtest/report.py` (200 LOC)
- `tests/test_report_generator.py`

**Acceptance:**
- HTML report opens in browser
- Charts interactive (if using plotly)
- All metrics displayed
- Report includes strategy config
- `make fmt lint type test` green

---

**Phase 5 Acceptance Criteria:**
- [ ] All 9 tasks completed
- [ ] `make fmt lint type test` green
- [ ] Backtest deterministic (same input → same output)
- [ ] Golden tests pass for known strategies
- [ ] Parameter sweep completes without errors
- [ ] Reports generated successfully
- [ ] Commission and slippage applied correctly
- [ ] Equity curves match manual calculations

---

## Integration with Existing System

### Backtest Flow
```
OHLCV Journals (Phase 4)
    ↓
JournalReader (4.7)
    ↓
Backtest Engine (5.2)
    ↓
Strategy.on_event() (Phase 3.8)
    ↓
OrderIntent
    ↓
Fill Simulator (5.3)
    ↓
Position Tracker
    ↓
Equity Curve (5.4)
    ↓
Performance Metrics (5.5)
    ↓
Report (5.9)
```

### Example Backtest Session
```bash
# 1. Run market data ingest (if not done)
make run-md SYMBOL=ATOM/USDT VENUE=binanceus

# 2. Wait for data collection (hours/days)
# ...

# 3. Stop ingest, verify journals exist
ls var/log/njord/ohlcv.1m.ATOMUSDT.*.ndjson

# 4. Run backtest
python -m backtest.runner \
    --strategy trendline_break_v1 \
    --symbol ATOM/USDT \
    --start 2025-01-01 \
    --end 2025-09-30 \
    --capital 10000

# 5. View report
open var/backtest/report_trendline_break_v1_ATOMUSDT.html

# 6. Optimize parameters
python -m backtest.param_sweep \
    --strategy trendline_break_v1 \
    --symbol ATOM/USDT \
    --param lookback_periods 10,20,30 \
    --param breakout_threshold 0.01,0.02,0.03
```

---

## Dependencies Summary

```
Phase 4 (OHLCV Storage) ✅
    └─> Phase 5.1 (Contracts)
            └─> 5.2 (Engine Core)
                    └─> 5.3 (Fill Sim)
                            └─> 5.4 (Equity Curve)
                                    └─> 5.5 (Metrics)
                                            ├─> 5.6 (CLI)
                                            ├─> 5.7 (Golden Tests)
                                            ├─> 5.8 (Param Sweep)
                                            └─> 5.9 (Reports)
```

Each task builds on the previous, maintaining clean separation of concerns.

---

## Phase 6 — Portfolio Allocator ✅

**Purpose:** Allocate capital across multiple strategies with risk-adjusted position sizing and rebalancing.

**Current Status:** Phase 5 complete — Backtester fully operational
**Next Phase:** Phase 7 — Research API

---

### Phase 6.1 — Portfolio Contracts ✅
**Status:** Complete
**Dependencies:** 5.9 (Backtest Report Generator)
**Task:** Define portfolio allocation contracts

**Contracts:**
```python
@dataclass(frozen=True)
class StrategyAllocation:
    """Capital allocation for a single strategy."""
    strategy_id: str
    target_weight: float  # 0.0 to 1.0 (percentage of total capital)
    min_capital: float    # Minimum capital required
    max_capital: float    # Maximum capital allowed
    risk_multiplier: float  # Adjust position sizes (1.0 = normal)

@dataclass(frozen=True)
class PortfolioConfig:
    """Portfolio-level configuration."""
    portfolio_id: str
    total_capital: float
    allocations: list[StrategyAllocation]
    rebalance_threshold: float  # Trigger rebalance if drift > threshold
    rebalance_frequency_hours: int  # Max time between rebalances

@dataclass(frozen=True)
class PortfolioSnapshot:
    """Current portfolio state."""
    portfolio_id: str
    timestamp_ns: int
    total_equity: float
    strategy_allocations: dict[str, float]  # strategy_id -> current capital
    drift_from_target: dict[str, float]  # strategy_id -> drift percentage
    needs_rebalance: bool
```

**Files:**
- `portfolio/contracts.py` (80 LOC)
- `tests/test_portfolio_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- Validation: weights sum to 1.0, min < max capital
- Serializable to/from dict
- `make fmt lint type test` green

---

### Phase 6.2 — Allocation Calculator ✅
**Status:** Complete
**Dependencies:** 6.1
**Task:** Calculate target capital allocations per strategy

**Behavior:**
- Input: `PortfolioConfig` + current market conditions
- Calculate target capital per strategy based on weights
- Apply min/max capital constraints
- Detect allocation drift (current vs. target)
- Return allocation recommendations

**API:**
```python
class AllocationCalculator:
    def __init__(self, config: PortfolioConfig): ...

    def calculate_targets(
        self,
        current_allocations: dict[str, float]
    ) -> dict[str, float]:
        """Calculate target allocations.

        Returns:
            Dict mapping strategy_id to target capital
        """
        pass

    def calculate_drift(
        self,
        current_allocations: dict[str, float],
        target_allocations: dict[str, float]
    ) -> dict[str, float]:
        """Calculate drift from target.

        Returns:
            Dict mapping strategy_id to drift percentage
        """
        pass

    def needs_rebalance(
        self,
        drift: dict[str, float]
    ) -> bool:
        """Check if rebalance is needed based on drift threshold."""
        pass
```

**Files:**
- `portfolio/allocator.py` (120 LOC)
- `tests/test_allocator.py`

**Acceptance:**
- Weights sum to 1.0 (with tolerance for rounding)
- Min/max constraints enforced
- Drift calculated correctly (relative to target)
- Rebalance trigger logic validated
- `make fmt lint type test` green

---

### Phase 6.3 — Position Sizer ✅
**Status:** Complete
**Dependencies:** 6.2
**Task:** Convert capital allocations to position sizes

**Behavior:**
- Take capital allocation per strategy
- Consider strategy risk multiplier
- Calculate position sizes for each symbol
- Apply portfolio-level risk limits
- Handle fractional shares/units

**API:**
```python
class PositionSizer:
    def __init__(self, config: PortfolioConfig): ...

    def calculate_position_size(
        self,
        strategy_id: str,
        symbol: str,
        allocated_capital: float,
        current_price: float
    ) -> float:
        """Calculate position size in units.

        Returns:
            Number of units to trade
        """
        pass

    def apply_risk_multiplier(
        self,
        base_size: float,
        risk_multiplier: float
    ) -> float:
        """Adjust position size by risk multiplier."""
        pass
```

**Files:**
- `portfolio/position_sizer.py` (100 LOC)
- `tests/test_position_sizer.py`

**Acceptance:**
- Position sizes match allocated capital
- Risk multipliers applied correctly
- Handles edge cases (zero capital, very high prices)
- Integer rounding for discrete units
- `make fmt lint type test` green

---

### Phase 6.4 — Rebalancer ✅
**Status:** Complete
**Dependencies:** 6.3
**Task:** Generate rebalancing trades to achieve target allocations

**Behavior:**
- Compare current vs. target allocations
- Generate `OrderIntent`s to rebalance
- Minimize trading costs (avoid small trades)
- Handle cash constraints
- Emit rebalancing plan

**API:**
```python
@dataclass(frozen=True)
class RebalancePlan:
    """Plan for rebalancing portfolio."""
    portfolio_id: str
    timestamp_ns: int
    trades: list[OrderIntent]
    expected_drift_reduction: dict[str, float]
    estimated_costs: float  # Commission + slippage

class Rebalancer:
    def __init__(
        self,
        allocator: AllocationCalculator,
        sizer: PositionSizer,
        min_trade_value: float = 10.0
    ): ...

    def create_rebalance_plan(
        self,
        snapshot: PortfolioSnapshot,
        current_prices: dict[str, float]
    ) -> RebalancePlan:
        """Generate rebalancing plan.

        Returns:
            RebalancePlan with trades to execute
        """
        pass
```

**Files:**
- `portfolio/rebalancer.py` (150 LOC)
- `tests/test_rebalancer.py`

**Acceptance:**
- Generates valid `OrderIntent`s
- Filters out sub-minimum trades
- Drift reduction calculated correctly
- Cost estimates include commission + slippage
- Test includes multi-strategy rebalance scenario
- `make fmt lint type test` green

---

### Phase 6.5 — Portfolio Tracker ✅
**Status:** Complete
**Dependencies:** 6.4
**Task:** Track portfolio state across multiple strategies

**Behavior:**
- Maintain current allocations per strategy
- Subscribe to fill events from all strategies
- Update strategy capitals on fills
- Calculate portfolio-level metrics
- Emit `PortfolioSnapshot` periodically

**API:**
```python
class PortfolioTracker:
    def __init__(self, config: PortfolioConfig): ...

    def on_fill(self, fill: FillEvent) -> None:
        """Update portfolio state on fill."""
        pass

    def get_snapshot(self) -> PortfolioSnapshot:
        """Get current portfolio snapshot."""
        pass

    def get_strategy_capital(self, strategy_id: str) -> float:
        """Get current capital for a strategy."""
        pass

    def get_total_equity(self) -> float:
        """Get total portfolio equity."""
        pass
```

**Files:**
- `portfolio/tracker.py` (120 LOC)
- `tests/test_portfolio_tracker.py`

**Acceptance:**
- Correctly tracks fills across strategies
- Capital allocations updated atomically
- Snapshot includes all required fields
- Handles concurrent updates gracefully
- `make fmt lint type test` green

---

### Phase 6.6 — Portfolio Manager Service ✅
**Status:** Complete
**Dependencies:** 6.5
**Task:** Orchestrate portfolio allocation and rebalancing

**Behavior:**
- Load `PortfolioConfig` from YAML
- Initialize allocator, sizer, rebalancer, tracker
- Subscribe to fill events from all strategies
- Periodically check for rebalance needs
- Execute rebalancing when threshold exceeded
- Publish `PortfolioSnapshot` to Redis
- Journal portfolio state to NDJSON

**CLI:**
```bash
python -m apps.portfolio_manager --config ./config/base.yaml
```

**Files:**
- `apps/portfolio_manager/main.py` (200 LOC)
- `config/portfolio.yaml` (example config)
- `tests/test_portfolio_manager.py`

**Acceptance:**
- Loads config and initializes components
- Subscribes to fills from multiple strategies
- Rebalances when drift exceeds threshold
- Publishes snapshots to Redis topic
- Journals state to `var/log/njord/portfolio.ndjson`
- `make fmt lint type test` green

---

### Phase 6.7 — Risk-Adjusted Allocation ✅
**Status:** Complete
**Dependencies:** 6.6
**Task:** Adjust allocations based on strategy performance metrics

**Behavior:**
- Track recent strategy performance (Sharpe, drawdown)
- Dynamically adjust risk multipliers
- Reduce allocation to underperforming strategies
- Increase allocation to outperforming strategies
- Apply constraints (min/max allocation bounds)

**API:**
```python
class RiskAdjustedAllocator:
    def __init__(
        self,
        base_allocator: AllocationCalculator,
        lookback_period_days: int = 30,
        adjustment_sensitivity: float = 0.1
    ): ...

    def calculate_adjusted_allocations(
        self,
        performance_history: dict[str, list[float]],  # strategy_id -> returns
        base_allocations: dict[str, float]
    ) -> dict[str, float]:
        """Calculate risk-adjusted allocations.

        Returns:
            Adjusted target allocations
        """
        pass
```

**Files:**
- `portfolio/risk_adjusted.py` (130 LOC)
- `tests/test_risk_adjusted.py`

**Acceptance:**
- Adjusts allocations based on Sharpe ratios
- Reduces allocation to high-drawdown strategies
- Respects min/max bounds from config
- Maintains total allocation = 100%
- Handles edge cases (all strategies losing)
- `make fmt lint type test` green

---

### Phase 6.8 — Portfolio Backtest Integration ✅
**Status:** Complete
**Dependencies:** 6.7, 5.6 (Backtest Runner)
**Task:** Run backtests with portfolio allocation

**Behavior:**
- Extend `BacktestEngine` to support portfolios
- Allocate capital across multiple strategies
- Track portfolio-level equity curve
- Generate portfolio-level metrics
- Compare portfolio vs. individual strategies

**API:**
```python
class PortfolioBacktestEngine:
    def __init__(
        self,
        portfolio_config: PortfolioConfig,
        strategies: dict[str, StrategyBase],
        journal_dir: Path
    ): ...

    def run(self) -> PortfolioBacktestResult:
        """Run portfolio backtest.

        Returns:
            Portfolio-level results with per-strategy breakdown
        """
        pass
```

**Files:**
- `backtest/portfolio_engine.py` (180 LOC)
- `tests/test_portfolio_backtest.py`

**Acceptance:**
- Runs multiple strategies concurrently
- Allocates capital per portfolio config
- Generates portfolio equity curve
- Calculates portfolio metrics (Sharpe, drawdown)
- Compares portfolio vs. sum of individual strategies
- `make fmt lint type test` green

---

### Phase 6.9 — Portfolio Report ✅
**Status:** Complete
**Dependencies:** 6.8
**Task:** Generate portfolio-level HTML reports

**Behavior:**
- Extend report generator for portfolios
- Show per-strategy allocation over time
- Display portfolio equity vs. individual strategies
- Breakdown of returns by strategy
- Allocation drift charts
- Rebalancing trade history

**Files:**
- `portfolio/report.py` (200 LOC)
- `tests/test_portfolio_report.py`

**Acceptance:**
- HTML report shows portfolio and per-strategy curves
- Allocation breakdown displayed as stacked area chart
- Rebalancing events marked on timeline
- Strategy contribution to returns calculated
- Report includes portfolio and strategy metrics tables
- `make fmt lint type test` green

---

**Phase 6 Acceptance Criteria:**
- [ ] All 9 tasks completed
- [ ] `make fmt lint type test` green
- [ ] Portfolio allocates capital across ≥2 strategies
- [ ] Rebalancing triggers when drift exceeds threshold
- [ ] Portfolio backtest runs successfully
- [ ] Portfolio reports generated with multi-strategy breakdown
- [ ] Risk-adjusted allocation adjusts to strategy performance
- [ ] Golden test validates portfolio vs. individual strategy returns

---

## Integration with Existing System

### Portfolio Flow
```
PortfolioConfig (6.1)
    ↓
AllocationCalculator (6.2) → Target Allocations
    ↓
PositionSizer (6.3) → Position Sizes per Strategy
    ↓
Rebalancer (6.4) → OrderIntents
    ↓
PortfolioTracker (6.5) ← FillEvents (from all strategies)
    ↓
PortfolioSnapshot → Published to Redis
    ↓
PortfolioManager (6.6) → Orchestrates all components
    ↓
RiskAdjustedAllocator (6.7) → Dynamic adjustment
    ↓
PortfolioBacktestEngine (6.8) → Historical testing
    ↓
PortfolioReport (6.9) → HTML visualization
```

### Example Portfolio Session
```bash
# 1. Configure portfolio
cat > config/portfolio.yaml <<EOF
portfolio:
  id: multi_strategy_v1
  total_capital: 50000.0
  rebalance_threshold: 0.05  # 5% drift
  rebalance_frequency_hours: 24

  allocations:
    - strategy_id: trendline_break_v1
      target_weight: 0.40
      min_capital: 10000.0
      max_capital: 30000.0
      risk_multiplier: 1.0

    - strategy_id: rsi_tema_bb_v1
      target_weight: 0.35
      min_capital: 10000.0
      max_capital: 25000.0
      risk_multiplier: 0.8

    - strategy_id: momentum_v1
      target_weight: 0.25
      min_capital: 5000.0
      max_capital: 20000.0
      risk_multiplier: 1.2
EOF

# 2. Run portfolio backtest
python -m backtest.portfolio_runner \
    --portfolio-config config/portfolio.yaml \
    --start 2025-01-01 \
    --end 2025-09-30 \
    --journal-dir var/log/njord

# 3. View portfolio report
open var/backtest/portfolio_multi_strategy_v1_report.html

# 4. Run live portfolio manager
python -m apps.portfolio_manager --config config/base.yaml
```

---

## Dependencies Summary

```
Phase 5 (Backtester) ✅
    └─> Phase 6.1 (Portfolio Contracts)
            └─> 6.2 (Allocation Calculator)
                    └─> 6.3 (Position Sizer)
                            └─> 6.4 (Rebalancer)
                                    └─> 6.5 (Portfolio Tracker)
                                            └─> 6.6 (Portfolio Manager)
                                                    ├─> 6.7 (Risk-Adjusted)
                                                    ├─> 6.8 (Portfolio Backtest)
                                                    └─> 6.9 (Portfolio Report)
```

Each task builds on the previous, maintaining clean separation of concerns.

---

## Phase 7 — Research API ✅

**Purpose:** Provide pandas/PyArrow interface for offline research, analysis, and strategy development.

**Current Status:** Phase 7 complete — Research API fully operational
**Next Phase:** Phase 8 — Execution Layer

---

### Phase 7.1 — Data Reader API ✅
**Status:** Complete
**Dependencies:** 4.7 (Journal Reader API)
**Task:** Create unified API for reading historical market data

**Behavior:**
- Read OHLCV bars from journals (NDJSON + compressed)
- Read trade ticks from journals
- Read fill events and position snapshots
- Time range filtering with nanosecond precision
- Symbol filtering (single or multiple)
- Return data as pandas DataFrames or PyArrow Tables
- Lazy loading for large datasets
- Memory-efficient iterators for streaming

**API:**
```python
class DataReader:
    def __init__(self, journal_dir: Path): ...

    def read_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas"
    ) -> pd.DataFrame | pa.Table:
        """Read OHLCV bars for a symbol/timeframe."""
        pass

    def read_trades(
        self,
        symbol: str,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas"
    ) -> pd.DataFrame | pa.Table:
        """Read trade ticks for a symbol."""
        pass

    def read_fills(
        self,
        strategy_id: str | None,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas"
    ) -> pd.DataFrame | pa.Table:
        """Read fill events (optionally filtered by strategy)."""
        pass

    def read_positions(
        self,
        portfolio_id: str,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas"
    ) -> pd.DataFrame | pa.Table:
        """Read portfolio snapshots."""
        pass
```

**Files:**
- `research/data_reader.py` (200 LOC)
- `tests/test_data_reader.py` (15 test cases)

**Acceptance:**
- Reads OHLCV, trades, fills, positions correctly
- Time range filtering accurate to nanosecond
- Both pandas and PyArrow output formats work
- Handles missing files gracefully (empty DataFrame)
- Compressed (.gz) files read transparently
- Test includes multi-symbol, multi-timeframe scenarios
- `make fmt lint type test` green

---

### Phase 7.2 — Data Aggregator ✅
**Status:** Complete
**Dependencies:** 7.1
**Task:** Aggregate raw data into research-friendly formats

**Behavior:**
- Resample OHLCV to different timeframes
- Compute rolling statistics (mean, std, min, max)
- Calculate technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- Merge multiple symbols into single DataFrame
- Forward-fill missing data (configurable)
- Alignment to wall-clock boundaries

**API:**
```python
class DataAggregator:
    def __init__(self, reader: DataReader): ...

    def resample_ohlcv(
        self,
        df: pd.DataFrame,
        target_timeframe: str,
        *,
        align_to_wall_clock: bool = True
    ) -> pd.DataFrame:
        """Resample OHLCV to different timeframe."""
        pass

    def add_indicators(
        self,
        df: pd.DataFrame,
        indicators: list[str]
    ) -> pd.DataFrame:
        """Add technical indicators to DataFrame.

        Supported indicators:
        - sma_N: Simple moving average (N periods)
        - ema_N: Exponential moving average
        - rsi_N: Relative strength index
        - macd: MACD (12, 26, 9)
        - bbands_N_K: Bollinger Bands (N periods, K std devs)
        """
        pass

    def merge_symbols(
        self,
        symbol_dfs: dict[str, pd.DataFrame],
        *,
        how: Literal["inner", "outer"] = "outer",
        fill_method: Literal["ffill", "none"] = "ffill"
    ) -> pd.DataFrame:
        """Merge multiple symbol DataFrames with aligned timestamps."""
        pass
```

**Files:**
- `research/aggregator.py` (180 LOC)
- `tests/test_aggregator.py` (12 test cases)

**Acceptance:**
- Resampling produces correct OHLCV (open=first, high=max, low=min, close=last, volume=sum)
- Indicators match known calculations (test against ta-lib or manual computation)
- Symbol merging aligns timestamps correctly
- Forward-fill works as expected
- Edge cases handled (single bar, empty DataFrame)
- `make fmt lint type test` green

---

### Phase 7.3 — Performance Analytics ✅
**Status:** Complete
**Dependencies:** 7.2, 5.5 (Backtest Metrics)
**Task:** Calculate research-focused performance metrics

**Behavior:**
- Extend backtest metrics for research use cases
- Time-series PnL analysis
- Drawdown duration and recovery statistics
- Win/loss distribution analysis
- Trade timing analysis (hour of day, day of week)
- Exposure analysis (time in market, leverage)
- Correlation with benchmark returns

**API:**
```python
class PerformanceAnalyzer:
    def __init__(self, fills_df: pd.DataFrame, positions_df: pd.DataFrame): ...

    def calculate_pnl_timeseries(
        self,
        *,
        resample_freq: str = "1D"
    ) -> pd.DataFrame:
        """Calculate PnL time series (daily, hourly, etc.)."""
        pass

    def analyze_drawdowns(self) -> pd.DataFrame:
        """Return DataFrame of drawdown periods with duration and recovery time."""
        pass

    def analyze_trade_distribution(self) -> dict[str, Any]:
        """Return statistics on trade sizes, durations, PnL distribution."""
        pass

    def analyze_trade_timing(self) -> pd.DataFrame:
        """Group trades by hour/day and calculate avg PnL."""
        pass

    def calculate_exposure(self) -> pd.DataFrame:
        """Time series of capital deployed (0 = all cash, 1 = fully invested)."""
        pass

    def correlation_with_benchmark(
        self,
        benchmark_returns: pd.Series
    ) -> dict[str, float]:
        """Calculate correlation, beta, alpha vs. benchmark."""
        pass
```

**Files:**
- `research/performance.py` (220 LOC)
- `tests/test_performance.py` (10 test cases)

**Acceptance:**
- PnL time series matches cumulative sum of fills
- Drawdown analysis identifies all local peaks correctly
- Trade distribution includes percentiles (25%, 50%, 75%)
- Timing analysis groups by hour/day correctly
- Exposure calculation handles multiple positions
- Correlation metrics match manual calculation
- `make fmt lint type test` green

---

### Phase 7.4 — Strategy Comparison Tool ✅
**Status:** Complete
**Dependencies:** 7.3
**Task:** Compare multiple strategies side-by-side

**Behavior:**
- Load results from multiple backtest runs
- Normalize equity curves to same starting capital
- Calculate relative performance metrics
- Generate comparison tables and charts
- Identify periods of outperformance/underperformance
- Statistical significance testing (t-test, bootstrap)

**API:**
```python
class StrategyComparison:
    def __init__(self, strategy_results: dict[str, BacktestResult]): ...

    def normalize_equity_curves(
        self,
        target_capital: float = 100000.0
    ) -> pd.DataFrame:
        """Normalize all equity curves to same starting capital."""
        pass

    def compare_metrics(self) -> pd.DataFrame:
        """Return DataFrame comparing all metrics across strategies."""
        pass

    def identify_divergence_periods(
        self,
        threshold: float = 0.1
    ) -> list[tuple[int, int, str, str]]:
        """Identify time periods where strategies diverged significantly.

        Returns:
            List of (start_ts, end_ts, outperformer, underperformer) tuples
        """
        pass

    def statistical_significance(
        self,
        strategy_a: str,
        strategy_b: str,
        *,
        method: Literal["ttest", "bootstrap"] = "ttest"
    ) -> dict[str, float]:
        """Test if performance difference is statistically significant.

        Returns:
            {"p_value": float, "confidence": float, "mean_diff": float}
        """
        pass
```

**Files:**
- `research/comparison.py` (150 LOC)
- `tests/test_comparison.py` (8 test cases)

**Acceptance:**
- Equity curves normalized correctly (all start at target_capital)
- Metrics comparison includes all strategies
- Divergence periods detected with correct threshold
- Statistical tests return valid p-values
- Handles edge cases (single strategy, identical results)
- `make fmt lint type test` green

---

### Phase 7.5 — Jupyter Integration ✅
**Status:** Complete
**Dependencies:** 7.4
**Task:** Create notebook-friendly helpers and example notebooks

**Behavior:**
- IPython magic commands for common operations
- Auto-reload for config changes
- Pretty-printing for contracts (orders, fills, positions)
- Plotting helpers using matplotlib
- Example notebooks for common workflows
- Ensure all operations work offline (no live data fetching)

**API:**
```python
# research/notebook_utils.py
def load_backtest_results(
    journal_dir: Path,
    strategy_ids: list[str]
) -> dict[str, BacktestResult]:
    """Load backtest results from journals."""
    pass

def plot_equity_curves(
    results: dict[str, BacktestResult],
    *,
    figsize: tuple[int, int] = (12, 6)
) -> Figure:
    """Plot equity curves for multiple strategies."""
    pass

def plot_drawdowns(
    equity_curve: pd.Series,
    *,
    figsize: tuple[int, int] = (12, 6)
) -> Figure:
    """Plot equity curve with drawdown periods shaded."""
    pass

def plot_monthly_returns_heatmap(
    pnl_series: pd.Series,
    *,
    figsize: tuple[int, int] = (10, 6)
) -> Figure:
    """Heatmap of monthly returns."""
    pass

def display_metrics_table(
    results: dict[str, BacktestResult]
) -> None:
    """Display formatted metrics table in Jupyter."""
    pass
```

**Example Notebooks:**
- `notebooks/01_data_exploration.ipynb` — Load and explore OHLCV data
- `notebooks/02_strategy_backtest.ipynb` — Run backtest and analyze results
- `notebooks/03_strategy_comparison.ipynb` — Compare multiple strategies
- `notebooks/04_parameter_optimization.ipynb` — Parameter sweep visualization

**Files:**
- `research/notebook_utils.py` (180 LOC)
- `notebooks/*.ipynb` (4 example notebooks)
- `tests/test_notebook_utils.py` (6 test cases)

**Acceptance:**
- All helper functions work in Jupyter environment
- Plots render correctly (test by saving to PNG)
- Example notebooks execute without errors (test via `nbconvert`)
- No network calls in any notebook code
- Pretty-printing formats contracts readably
- `make fmt lint type test` green

---

### Phase 7.6 — Data Export Utilities ✅
**Status:** Complete
**Dependencies:** 7.5
**Task:** Export data to various formats for external tools

**Behavior:**
- Export to CSV (Excel-compatible)
- Export to Parquet (for Arrow ecosystem)
- Export to HDF5 (for large datasets)
- Export to JSON (for web visualization)
- Compression options for each format
- Schema preservation (column types, index)

**API:**
```python
class DataExporter:
    def __init__(self, data_reader: DataReader): ...

    def export_ohlcv_to_csv(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        output_path: Path
    ) -> None:
        """Export OHLCV to CSV."""
        pass

    def export_ohlcv_to_parquet(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        output_path: Path,
        *,
        compression: Literal["snappy", "gzip", "none"] = "snappy"
    ) -> None:
        """Export OHLCV to Parquet."""
        pass

    def export_backtest_results_to_json(
        self,
        results: dict[str, BacktestResult],
        output_path: Path,
        *,
        indent: int | None = 2
    ) -> None:
        """Export backtest results to JSON."""
        pass

    def export_fills_to_csv(
        self,
        strategy_id: str | None,
        start_ts: int,
        end_ts: int,
        output_path: Path
    ) -> None:
        """Export fill events to CSV."""
        pass
```

**Files:**
- `research/export.py` (140 LOC)
- `tests/test_export.py` (8 test cases)

**Acceptance:**
- CSV exports are Excel-compatible (proper date formatting)
- Parquet files readable by Arrow/Pandas
- JSON exports are valid and human-readable
- Compression reduces file size by >50% (test with sample data)
- Exported data matches source data exactly (round-trip test)
- `make fmt lint type test` green

---

### Phase 7.7 — Data Validation Tools ✅
**Status:** Complete
**Dependencies:** 7.6
**Task:** Validate data quality and detect anomalies

**Behavior:**
- Check for missing timestamps (gaps in time series)
- Detect price anomalies (spikes, flatlines)
- Validate OHLCV consistency (high ≥ low, close within [low, high])
- Check for volume spikes
- Identify suspicious fills (price deviation from market)
- Report generation for data quality issues

**API:**
```python
class DataValidator:
    def __init__(self, reader: DataReader): ...

    def check_gaps(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int
    ) -> list[tuple[int, int]]:
        """Identify gaps in time series.

        Returns:
            List of (gap_start_ts, gap_end_ts) tuples
        """
        pass

    def check_price_anomalies(
        self,
        df: pd.DataFrame,
        *,
        spike_threshold: float = 0.1,  # 10% move
        flatline_periods: int = 10  # consecutive identical prices
    ) -> dict[str, list[int]]:
        """Detect price spikes and flatlines.

        Returns:
            {"spikes": [ts1, ts2, ...], "flatlines": [ts1, ts2, ...]}
        """
        pass

    def validate_ohlcv_consistency(
        self,
        df: pd.DataFrame
    ) -> list[dict[str, Any]]:
        """Check OHLCV bar consistency.

        Returns:
            List of inconsistencies: [{"ts": ts, "issue": "high < low"}, ...]
        """
        pass

    def check_fill_anomalies(
        self,
        fills_df: pd.DataFrame,
        market_prices_df: pd.DataFrame,
        *,
        deviation_threshold: float = 0.02  # 2% from market
    ) -> list[dict[str, Any]]:
        """Identify fills with suspicious prices."""
        pass

    def generate_quality_report(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int
    ) -> dict[str, Any]:
        """Generate comprehensive data quality report."""
        pass
```

**Files:**
- `research/validation.py` (160 LOC)
- `tests/test_validation.py` (10 test cases)

**Acceptance:**
- Gap detection identifies all missing periods correctly
- Spike detection uses rolling z-score or percentage change
- OHLCV validation catches all constraint violations
- Fill anomaly detection compares to market data
- Quality report includes summary statistics
- `make fmt lint type test` green

---

### Phase 7.8 — Research CLI ✅
**Status:** Complete
**Dependencies:** 7.7
**Task:** Command-line interface for research operations

**Behavior:**
- Export data to various formats
- Run data validation checks
- Generate summary statistics
- Compare backtest results
- List available data (symbols, timeframes, date ranges)

**CLI Commands:**
```bash
# Export data
python -m research.cli export-ohlcv \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2025-01-01 \
    --end 2025-09-30 \
    --format csv \
    --output data/atom_1m.csv

# Validate data quality
python -m research.cli validate \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2025-01-01 \
    --end 2025-09-30

# List available data
python -m research.cli list-data

# Compare backtest results
python -m research.cli compare-backtests \
    --results var/backtest/strategy_a.json \
    --results var/backtest/strategy_b.json \
    --output comparison.csv
```

**Files:**
- `research/cli.py` (150 LOC)
- `tests/test_research_cli.py` (8 test cases)

**Acceptance:**
- All CLI commands parse arguments correctly
- Export commands create files in correct format
- Validate command outputs human-readable report
- List command shows all available data
- Compare command generates CSV with metrics
- Help text is complete and accurate
- `make fmt lint type test` green

---

### Phase 7.9 — Research API Documentation ✅
**Status:** Complete
**Dependencies:** 7.8
**Task:** Generate API documentation and usage guides

**Behavior:**
- Sphinx documentation for all research modules
- API reference with examples
- Usage guides for common workflows
- Jupyter notebook tutorials
- Type stubs for IDE autocomplete

**Deliverables:**
- Sphinx configuration (`docs/conf.py`)
- API documentation (auto-generated from docstrings)
- User guide (`docs/research_guide.md`)
- Tutorial notebooks (already in 7.5)
- Type stubs (`.pyi` files for key modules)

**Files:**
- `docs/conf.py` (Sphinx configuration)
- `docs/research_guide.md` (usage guide)
- `research/*.pyi` (type stubs for autocomplete)
- `tests/test_docs_build.py` (ensure docs build without errors)

**Acceptance:**
- Sphinx builds documentation without errors
- All public APIs documented with examples
- Usage guide covers common workflows
- Type stubs enable IDE autocomplete
- No broken links in documentation
- `make fmt lint type test` green

---

**Phase 7 Acceptance Criteria:**
- [ ] All 9 tasks completed
- [ ] `make fmt lint type test` green
- [ ] Data reader loads OHLCV, trades, fills, positions
- [ ] Aggregator produces correct indicators and resampling
- [ ] Performance analyzer calculates all metrics correctly
- [ ] Strategy comparison identifies divergence periods
- [ ] Jupyter helpers work in notebook environment
- [ ] Export utilities create valid files in all formats
- [ ] Data validator detects anomalies correctly
- [ ] CLI commands execute without errors
- [ ] Documentation builds and is comprehensive

---

## Integration with Existing System

### Research Flow
```
OHLCV Journals (Phase 4)
    ↓
DataReader (7.1) → pandas/Arrow DataFrames
    ↓
DataAggregator (7.2) → Technical Indicators
    ↓
PerformanceAnalyzer (7.3) → Metrics & Statistics
    ↓
StrategyComparison (7.4) → Side-by-side Analysis
    ↓
Jupyter Notebooks (7.5) → Interactive Exploration
    ↓
DataExporter (7.6) → CSV/Parquet/JSON
    ↓
DataValidator (7.7) → Quality Checks
    ↓
Research CLI (7.8) → Command-line Tools
```

### Example Research Session
```bash
# 1. List available data
python -m research.cli list-data

# 2. Validate data quality
python -m research.cli validate \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2025-01-01 \
    --end 2025-09-30

# 3. Export to Parquet for analysis
python -m research.cli export-ohlcv \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2025-01-01 \
    --end 2025-09-30 \
    --format parquet \
    --output data/atom_1m.parquet

# 4. Launch Jupyter for interactive analysis
jupyter lab notebooks/02_strategy_backtest.ipynb

# 5. Compare multiple backtest results
python -m research.cli compare-backtests \
    --results var/backtest/*.json \
    --output comparison.csv
```

---

## Dependencies Summary

```
Phase 4 (OHLCV Storage) ✅
    └─> Phase 5 (Backtester) ✅
            └─> Phase 6 (Portfolio) ✅
                    └─> Phase 7.1 (Data Reader)
                            └─> 7.2 (Aggregator)
                                    └─> 7.3 (Performance)
                                            └─> 7.4 (Comparison)
                                                    ├─> 7.5 (Jupyter)
                                                    ├─> 7.6 (Export)
                                                    ├─> 7.7 (Validation)
                                                    ├─> 7.8 (CLI)
                                                    └─> 7.9 (Docs)
```

Each task builds on the previous, maintaining clean separation of concerns.

---

## Phase 8 — Execution Layer 📋

**Purpose:** Implement sophisticated order execution algorithms, smart routing, and realistic slippage/fee simulation.

**Current Status:** Phase 7 complete — Research API fully operational
**Next Phase:** Phase 9 — Metrics & Telemetry

---

### Phase 8.0 — Execution Layer Foundations 📋
**Status:** Planned
**Dependencies:** 7.9 (Research API Documentation)
**Task:** Establish architectural foundations for execution layer

**Critical Architectural Requirements:**
1. **No Risk Engine Bypass:** Execution algorithms must emit `OrderIntent` and go through risk engine, NOT call broker directly
2. **Bus Protocol Layering:** Move `BusProto` from app-level to `core/bus.py` as framework interface
3. **Async/Sync Reconciliation:** Establish patterns for async executors with sync broker interface
4. **Timestamp Consistency:** Use `*_ns` suffix for all nanosecond timestamps
5. **Slice-to-Fill Tracking:** Map execution slices back to fills via client_order_id

**Deliverables:**

#### 1. Bus Protocol (Framework-Level)
```python
# core/bus.py (extend existing)
class BusProto(Protocol):
    """Bus protocol for pub/sub operations.

    IMPORTANT: Must match existing Bus implementation signature exactly.
    """

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish JSON payload to topic."""
        ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to topic, yield messages.

        Note: This is a SYNC method returning AsyncIterator (not async def).
        Existing usage: async for msg in bus.subscribe(topic)  # No await!
        """
        ...
```

#### 2. Execution Architecture Pattern
```python
# Executors emit OrderIntent, NOT broker calls
class BaseExecutor(ABC):
    def __init__(self, strategy_id: str): ...

    @abstractmethod
    async def plan_execution(
        self,
        algo: ExecutionAlgorithm
    ) -> list[OrderIntent]:
        """Plan execution, return OrderIntents for risk engine."""
        pass

    async def track_fills(
        self,
        bus: BusProto,
        execution_id: str
    ) -> AsyncIterator[FillEvent]:
        """Subscribe to fills.new, filter by execution_id."""
        pass
```

#### 3. Async/Sync Adapter Pattern
```python
# execution/adapters.py
class SyncExecutionWrapper:
    """Wrap async executor for sync contexts (backtest).

    WARNING: Uses asyncio.run() which creates a new event loop.
    - Safe in pure sync contexts (backtest engine)
    - FAILS if called from within an existing event loop
    - Do NOT use in async services (risk_engine, broker, etc.)
    """

    def __init__(self, async_executor: BaseExecutor): ...

    def plan_execution_sync(
        self,
        algo: ExecutionAlgorithm
    ) -> list[OrderIntent]:
        """Synchronous wrapper for async executor.

        Raises:
            RuntimeError: If called from within an existing event loop
        """
        # Safe only in pure sync contexts (backtest)
        return asyncio.run(self.async_executor.plan_execution(algo))
```

**Files:**
- `core/bus.py` (add BusProto, ~30 LOC)
- `execution/base.py` (BaseExecutor ABC, ~80 LOC)
- `execution/adapters.py` (sync/async wrappers, ~60 LOC)
- `tests/test_execution_base.py`

**Acceptance:**
- BusProto defined in core/bus.py (framework-level)
- BusProto.subscribe signature matches existing Bus (def, not async def)
- BaseExecutor ABC enforces OrderIntent emission (no broker calls)
- Sync wrapper pattern documented with asyncio.run() warnings
- SyncExecutionWrapper only used in pure sync contexts (backtest)
- All timestamps use `*_ns` suffix convention
- Execution slice client_order_id maps to OrderIntent.intent_id
- **CRITICAL: Child OrderIntents must pack execution_id and slice_id into OrderIntent.meta for fill tracking**
- **Test verifies round-trip: OrderIntent.meta → Fill → ExecutionReport recovery**
- Test verifies asyncio.run() raises in existing event loop
- `make fmt lint type test` green

---

### Phase 8.1 — Execution Contracts 📋
**Status:** Planned
**Dependencies:** 8.0 (Execution Layer Foundations)
**Task:** Define execution-specific contracts

**Contracts:**
```python
@dataclass(frozen=True)
class ExecutionAlgorithm:
    """Configuration for execution algorithm."""
    algo_type: Literal["TWAP", "VWAP", "Iceberg", "POV"]  # Percentage of Volume
    symbol: str
    side: Literal["buy", "sell"]
    total_quantity: float
    duration_seconds: int
    params: dict[str, Any]  # Algorithm-specific parameters

@dataclass(frozen=True)
class ExecutionSlice:
    """Individual slice of parent execution order."""
    execution_id: str
    slice_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    limit_price: float | None
    scheduled_ts_ns: int  # When to execute this slice (nanoseconds)
    status: Literal["pending", "submitted", "filled", "cancelled"]
    client_order_id: str  # Maps to OrderIntent.intent_id

@dataclass(frozen=True)
class ExecutionReport:
    """Progress report for execution algorithm."""
    execution_id: str
    symbol: str
    total_quantity: float
    filled_quantity: float
    remaining_quantity: float
    avg_fill_price: float
    total_fees: float
    slices_completed: int
    slices_total: int
    status: Literal["running", "completed", "cancelled", "failed"]
    start_ts_ns: int
    end_ts_ns: int | None
```

**Files:**
- `execution/contracts.py` (100 LOC)
- `tests/test_execution_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix (scheduled_ts_ns, start_ts_ns, end_ts_ns)
- ExecutionSlice includes client_order_id for fill tracking
- Serializable to/from dict
- Validation: total_quantity > 0, duration_seconds > 0
- `make fmt lint type test` green

---

### Phase 8.2 — TWAP Algorithm 📋
**Status:** Planned
**Dependencies:** 8.1 (Execution Contracts)
**Task:** Implement Time-Weighted Average Price execution

**Behavior:**
- Split total order into N equal slices over duration
- Generate `OrderIntent` for each slice at regular intervals: `duration / N`
- Use limit orders at current mid-price or market orders
- Track fills via `fills.new` topic subscription
- Generate cancel intents for unfilled slices at end of duration
- **NO DIRECT BROKER CALLS** — emit OrderIntent only

**API:**
```python
class TWAPExecutor(BaseExecutor):
    def __init__(
        self,
        strategy_id: str,
        slice_count: int = 10,
        order_type: Literal["limit", "market"] = "limit"
    ): ...

    async def plan_execution(
        self,
        algo: ExecutionAlgorithm
    ) -> list[OrderIntent]:
        """Plan TWAP execution as OrderIntents.

        Returns:
            List of OrderIntent (one per slice)
        """
        pass

    def _create_slice_intent(
        self,
        execution_id: str,
        slice_idx: int,
        quantity: float,
        scheduled_ts_ns: int,
        current_price: float
    ) -> OrderIntent:
        """Create OrderIntent for individual slice.

        IMPORTANT: Must pack execution_id and slice_id into OrderIntent.meta:
            meta = {
                "execution_id": execution_id,
                "slice_id": f"{execution_id}_{slice_idx}",
                ...
            }
        This enables fill tracking and ExecutionReport recovery.
        """
        pass

    async def _monitor_fills(
        self,
        bus: BusProto,
        execution_id: str
    ) -> ExecutionReport:
        """Track fills and build execution report."""
        pass
```

**Files:**
- `execution/twap.py` (150 LOC)
- `tests/test_twap_executor.py`

**Acceptance:**
- Returns list[OrderIntent], NO broker calls
- Slices scheduled at correct intervals (scheduled_ts_ns)
- Total quantity distributed evenly across slices
- **Each OrderIntent.meta includes execution_id and slice_id for fill tracking**
- Cancel intents generated for unfilled slices
- Fill tracking via bus subscription works correctly (recovers execution_id from FillEvent metadata)
- Execution report tracks progress correctly
- Test includes partial fill scenario
- **Test verifies OrderIntent.meta → FillEvent → ExecutionReport round-trip**
- `make fmt lint type test` green

---

### Phase 8.3 — VWAP Algorithm 📋
**Status:** Planned
**Dependencies:** 8.2 (TWAP Algorithm)
**Task:** Implement Volume-Weighted Average Price execution

**Behavior:**
- Fetch historical volume distribution (hourly/daily)
- Weight slices based on expected volume profile
- Generate OrderIntent for larger slices during high-volume periods
- Dynamically adjust if actual volume diverges
- Track VWAP benchmark vs. execution price
- **NO DIRECT BROKER CALLS** — emit OrderIntent only

**API:**
```python
class VWAPExecutor(BaseExecutor):
    def __init__(
        self,
        strategy_id: str,
        data_reader: DataReader,
        lookback_days: int = 7
    ): ...

    async def plan_execution(
        self,
        algo: ExecutionAlgorithm
    ) -> list[OrderIntent]:
        """Plan VWAP execution as OrderIntents.

        Returns:
            List of OrderIntent (weighted by volume)
        """
        pass

    def _calculate_volume_profile(
        self,
        symbol: str,
        duration_seconds: int
    ) -> list[float]:
        """Calculate expected volume distribution.

        Returns:
            List of volume weights summing to 1.0
        """
        pass

    def _create_weighted_intent(
        self,
        execution_id: str,
        slice_idx: int,
        weight: float,
        total_quantity: float,
        scheduled_ts_ns: int,
        current_price: float
    ) -> OrderIntent:
        """Create OrderIntent for volume-weighted slice.

        IMPORTANT: Must pack execution_id and slice_id into OrderIntent.meta for fill tracking.
        """
        pass
```

**Files:**
- `execution/vwap.py` (180 LOC)
- `tests/test_vwap_executor.py`

**Acceptance:**
- Returns list[OrderIntent], NO broker calls
- Volume profile calculated from historical data
- Slices weighted correctly by volume
- **Each OrderIntent.meta includes execution_id and slice_id for fill tracking**
- VWAP tracking accurate vs. benchmark
- Handles missing volume data gracefully
- Test includes volume distribution validation
- **Test verifies OrderIntent.meta → FillEvent round-trip**
- `make fmt lint type test` green

---

### Phase 8.4 — Iceberg Orders 📋
**Status:** Planned
**Dependencies:** 8.3 (VWAP Algorithm)
**Task:** Implement iceberg order execution (show small, hide large)

**Behavior:**
- Generate OrderIntent for small "visible" quantity initially
- Monitor fills and emit replenishment OrderIntent when threshold reached
- Hide total order size from market
- Avoid moving market with large orders
- Support multiple price levels
- **NO DIRECT BROKER CALLS** — emit OrderIntent only

**API:**
```python
class IcebergExecutor(BaseExecutor):
    def __init__(
        self,
        strategy_id: str,
        visible_ratio: float = 0.1,  # 10% visible
        replenish_threshold: float = 0.5  # Replenish at 50% fill
    ): ...

    async def plan_execution(
        self,
        algo: ExecutionAlgorithm
    ) -> list[OrderIntent]:
        """Plan initial iceberg OrderIntent.

        Returns:
            List with single OrderIntent for visible portion
        """
        pass

    def _create_visible_intent(
        self,
        execution_id: str,
        visible_qty: float,
        limit_price: float,
        scheduled_ts_ns: int
    ) -> OrderIntent:
        """Create OrderIntent for visible portion of iceberg.

        IMPORTANT: Must pack execution_id and slice_id into OrderIntent.meta for fill tracking.
        """
        pass

    async def _monitor_and_replenish(
        self,
        bus: BusProto,
        execution_id: str,
        algo: ExecutionAlgorithm
    ) -> AsyncIterator[OrderIntent]:
        """Monitor fills, yield replenishment OrderIntents."""
        pass
```

**Files:**
- `execution/iceberg.py` (140 LOC)
- `tests/test_iceberg_executor.py`

**Acceptance:**
- Returns list[OrderIntent], NO broker calls
- Only visible_ratio quantity in initial intent
- Replenishment intents generated when threshold reached
- **Each OrderIntent.meta includes execution_id and slice_id for fill tracking**
- Total quantity hidden from market view
- Handles partial fills correctly
- Test includes multiple replenishment cycles
- **Test verifies OrderIntent.meta → FillEvent round-trip for replenishment**
- `make fmt lint type test` green

---

### Phase 8.5 — POV Algorithm 📋
**Status:** Planned
**Dependencies:** 8.4 (Iceberg Orders)
**Task:** Implement Percentage of Volume execution

**Behavior:**
- Target participation rate (e.g., 20% of market volume)
- Monitor real-time volume via market data
- Generate OrderIntent with sizes to maintain target %
- Pause if volume too low (no intent emission)
- Accelerate if behind schedule
- **NO DIRECT BROKER CALLS** — emit OrderIntent only

**API:**
```python
class POVExecutor(BaseExecutor):
    def __init__(
        self,
        strategy_id: str,
        data_reader: DataReader,
        target_pov: float = 0.2,  # 20% of volume
        min_volume_threshold: float = 1000.0
    ): ...

    async def plan_execution(
        self,
        algo: ExecutionAlgorithm
    ) -> list[OrderIntent]:
        """Plan POV execution as OrderIntents.

        Returns:
            List of OrderIntent (dynamically sized by volume)
        """
        pass

    async def _monitor_volume(
        self,
        bus: BusProto,
        symbol: str
    ) -> float:
        """Monitor real-time market volume.

        Returns:
            Volume in last measurement period
        """
        pass

    def _calculate_slice_size(
        self,
        market_volume: float,
        remaining_quantity: float,
        time_remaining_ns: int
    ) -> float:
        """Calculate next slice size based on POV target."""
        pass
```

**Files:**
- `execution/pov.py` (170 LOC)
- `tests/test_pov_executor.py`

**Acceptance:**
- Returns list[OrderIntent], NO broker calls
- Maintains target POV within 5% tolerance
- **Each OrderIntent.meta includes execution_id and slice_id for fill tracking**
- No intents emitted when volume below threshold
- Accelerates to catch up if behind
- Handles volume spikes gracefully
- Test includes varying volume scenarios
- **Test verifies OrderIntent.meta → FillEvent round-trip for dynamic slicing**
- `make fmt lint type test` green

---

### Phase 8.6 — Slippage Model 📋
**Status:** Planned
**Dependencies:** 8.5
**Task:** Implement realistic slippage simulation for backtesting

**Behavior:**
- Model slippage based on order size vs. volume
- Price impact function: `impact = f(order_size / avg_volume)`
- Temporary vs. permanent impact
- Bid-ask spread crossing costs
- Support multiple slippage models (linear, square-root, etc.)

**API:**
```python
class SlippageModel(ABC):
    @abstractmethod
    def calculate_slippage(
        self,
        order_size: float,
        market_volume: float,
        bid_ask_spread: float,
        reference_price: float
    ) -> float:
        """Calculate expected slippage in price units.

        Args:
            order_size: Order quantity
            market_volume: Average market volume
            bid_ask_spread: Current bid-ask spread
            reference_price: Reference price for impact calculation
        """
        pass

class LinearSlippageModel(SlippageModel):
    def __init__(self, impact_coefficient: float = 0.001): ...

    def calculate_slippage(
        self,
        order_size: float,
        market_volume: float,
        bid_ask_spread: float,
        reference_price: float
    ) -> float:
        """Linear slippage: impact_coef * (order_size / volume) * reference_price."""
        pass

class SquareRootSlippageModel(SlippageModel):
    def __init__(self, impact_coefficient: float = 0.5): ...

    def calculate_slippage(
        self,
        order_size: float,
        market_volume: float,
        bid_ask_spread: float,
        reference_price: float
    ) -> float:
        """Square-root slippage: impact_coef * sqrt(order_size / volume) * reference_price."""
        pass
```

**Files:**
- `execution/slippage.py` (120 LOC)
- `tests/test_slippage_model.py`

**Acceptance:**
- Linear model produces expected slippage (includes reference_price in calculation)
- Square-root model matches empirical data (includes reference_price in calculation)
- Bid-ask spread cost added correctly
- Handles edge cases (zero volume, huge orders)
- Test validates reference_price is used in slippage calculation (not just order_size/volume)
- Test includes calibration to real data
- `make fmt lint type test` green

---

### Phase 8.7 — Execution Simulator 📋
**Status:** Planned
**Dependencies:** 8.6 (Slippage Model)
**Task:** Integrate execution algorithms into backtest engine

**Behavior:**
- Extend `BacktestEngine` to use execution algorithms
- Simulate TWAP/VWAP/Iceberg/POV in backtests
- Apply slippage models to fills
- Track execution quality metrics (vs. arrival price, VWAP)
- Compare algorithm performance
- **Provide sync interface for backtest compatibility**

**API:**
```python
class ExecutionSimulator:
    def __init__(
        self,
        slippage_model: SlippageModel,
        data_reader: DataReader
    ): ...

    def simulate_execution(
        self,
        algo: ExecutionAlgorithm,
        market_data: pd.DataFrame
    ) -> ExecutionReport:
        """Simulate execution algorithm in backtest (SYNC).

        Args:
            algo: Execution algorithm config
            market_data: OHLCV bars for simulation period

        Returns:
            Execution report with fills
        """
        pass

    def _plan_and_execute(
        self,
        executor: BaseExecutor,
        algo: ExecutionAlgorithm,
        market_data: pd.DataFrame
    ) -> list[FillEvent]:
        """Plan execution via executor, simulate fills."""
        # Uses SyncExecutionWrapper internally
        pass

    def _apply_slippage(
        self,
        intent: OrderIntent,
        market_price: float,
        market_volume: float,
        scheduled_ts_ns: int
    ) -> FillEvent:
        """Apply slippage model to OrderIntent execution."""
        pass
```

**Files:**
- `execution/simulator.py` (180 LOC)
- `tests/test_execution_simulator.py`

**Acceptance:**
- Synchronous interface compatible with backtest engine
- TWAP/VWAP/Iceberg/POV simulated correctly via OrderIntent flow
- Slippage applied to all fills
- Uses SyncExecutionWrapper to call async executors
- Execution quality metrics calculated
- Integration with backtest engine seamless
- Test includes multi-algo comparison
- `make fmt lint type test` green

---

### Phase 8.8 — Smart Order Router 📋
**Status:** Planned
**Dependencies:** 8.7 (Execution Simulator)
**Task:** Route orders to best execution venue/algorithm

**Behavior:**
- Evaluate order characteristics (size, urgency, symbol)
- Select optimal execution algorithm
- Orchestrate execution via selected executor
- Publish resulting OrderIntents to bus
- Monitor execution quality
- Learn from historical performance
- **Acts as orchestrator, NOT executor** — publishes OrderIntents

**API:**
```python
class SmartOrderRouter:
    def __init__(
        self,
        bus: BusProto,
        executors: dict[str, BaseExecutor],  # algo_type -> executor
        performance_tracker: ExecutionPerformanceTracker
    ): ...

    async def route_order(
        self,
        parent_intent: OrderIntent,
        urgency_seconds: int | None = None
    ) -> str:
        """Route order to optimal execution.

        Returns:
            Execution ID for tracking
        """
        pass

    def _select_algorithm(
        self,
        intent: OrderIntent,
        urgency_seconds: int | None,
        market_conditions: dict[str, Any]
    ) -> str:
        """Select best execution algorithm.

        Returns:
            Algorithm type (TWAP, VWAP, Iceberg, POV)
        """
        pass

    async def _orchestrate_execution(
        self,
        executor: BaseExecutor,
        algo: ExecutionAlgorithm
    ) -> None:
        """Orchestrate execution: plan + publish OrderIntents."""
        # Gets OrderIntents from executor, publishes to strat.intent
        pass
```

**Files:**
- `execution/router.py` (200 LOC)
- `tests/test_smart_router.py`

**Acceptance:**
- Algorithm selection based on order size/urgency
- Publishes OrderIntents to bus (no direct broker calls)
- Performance tracking influences routing decisions
- Handles executor failures gracefully
- Test includes routing decision validation
- Multi-venue support (venue in OrderIntent metadata)
- `make fmt lint type test` green

---

### Phase 8.9 — Execution Performance Metrics 📋
**Status:** Planned
**Dependencies:** 8.8
**Task:** Track and analyze execution quality

**Behavior:**
- Calculate execution benchmarks (arrival price, VWAP, etc.)
- Implementation shortfall analysis
- Slippage attribution (market impact vs. timing)
- Algorithm performance comparison
- Venue quality scoring

**API:**
```python
class ExecutionPerformanceTracker:
    def __init__(self, data_reader: DataReader): ...

    def calculate_implementation_shortfall(
        self,
        report: ExecutionReport,
        arrival_price: float
    ) -> dict[str, float]:
        """Calculate implementation shortfall.

        Returns:
            {
                "total_shortfall_bps": float,
                "market_impact_bps": float,
                "timing_cost_bps": float,
                "fees_bps": float
            }
        """
        pass

    def compare_to_benchmark(
        self,
        report: ExecutionReport,
        benchmark: Literal["arrival", "vwap", "twap"]
    ) -> float:
        """Compare execution to benchmark.

        Returns:
            Difference in basis points (positive = worse than benchmark)
        """
        pass

    def analyze_algorithm_performance(
        self,
        reports: list[ExecutionReport]
    ) -> pd.DataFrame:
        """Analyze performance across executions.

        Returns:
            DataFrame with metrics per algorithm/venue
        """
        pass

    def score_venue_quality(
        self,
        venue: str,
        symbol: str,
        lookback_days: int = 30
    ) -> dict[str, float]:
        """Score venue execution quality.

        Returns:
            {"avg_slippage_bps": float, "fill_rate": float, "avg_latency_ms": float}
        """
        pass
```

**Files:**
- `execution/performance.py` (200 LOC)
- `tests/test_execution_performance.py`

**Acceptance:**
- Implementation shortfall calculated correctly
- Benchmark comparisons accurate (test vs. known values)
- Algorithm performance metrics comprehensive
- Venue scoring includes latency/fill rate/slippage
- Test includes edge cases (zero slippage, failed fills)
- `make fmt lint type test` green

---

**Phase 8 Acceptance Criteria:**
- [ ] All 10 tasks completed (8.0-8.9)
- [ ] `make fmt lint type test` green
- [ ] BusProto moved to core/bus.py (framework-level)
- [ ] All executors inherit from BaseExecutor (no broker dependencies)
- [ ] All executors return list[OrderIntent] (no direct broker calls)
- [ ] All timestamps use `*_ns` suffix convention
- [ ] Sync/async adapter pattern documented and tested
- [ ] TWAP/VWAP/Iceberg/POV algorithms implemented and tested
- [ ] Slippage models calibrated and validated
- [ ] Execution simulator uses sync interface for backtest compatibility
- [ ] Smart order router orchestrates via OrderIntent publication
- [ ] Performance metrics track execution quality
- [ ] All execution contracts immutable and typed
- [ ] Golden tests validate deterministic execution
- [ ] Execution flow respects risk engine (no bypass)

---

## Integration with Existing System

### Execution Flow (Corrected Architecture)
```
OrderIntent (from Strategy)
    ↓
Smart Order Router (8.8) — Algorithm Selection
    ↓
Selected Executor (TWAP/VWAP/Iceberg/POV) — plan_execution()
    ↓
list[OrderIntent] (child orders/slices)
    ↓
Published to strat.intent topic
    ↓
Risk Engine (Phase 2.3) — Enforce caps, kill-switch
    ↓
RiskDecision + OrderEvent
    ↓
Broker (Phase 3) — Place orders
    ↓
FillEvent
    ↓
Execution Tracking (8.9) — Build ExecutionReport
    ↓
Performance Metrics
```

**Key Architectural Guarantees:**
- ✅ All execution algorithms go through risk engine
- ✅ No direct broker calls from executors
- ✅ Kill-switch enforcement maintained
- ✅ Async/sync compatibility via adapters
- ✅ Framework-level bus protocol (core/bus.py)

### Example Execution Session
```bash
# 1. Configure execution algorithms
cat > config/execution.yaml <<EOF
execution:
  algorithms:
    - type: TWAP
      default_slices: 10
      order_type: limit

    - type: VWAP
      lookback_days: 7
      min_volume_threshold: 1000

    - type: Iceberg
      visible_ratio: 0.1
      replenish_threshold: 0.5

    - type: POV
      target_pov: 0.2
      min_volume_threshold: 1000

  slippage:
    model: square_root
    impact_coefficient: 0.5

  routing:
    default_algo: TWAP
    large_order_threshold: 10000.0  # Use VWAP for orders > 10k USD
    urgency_threshold: 300  # seconds
EOF

# 2. Run backtest with execution simulation
python -m backtest.runner \
    --strategy trendline_break_v1 \
    --symbol ATOM/USDT \
    --start 2025-01-01 \
    --end 2025-09-30 \
    --execution-config config/execution.yaml \
    --capital 10000

# 3. Analyze execution performance
python -m execution.analyze \
    --execution-reports var/backtest/executions.ndjson \
    --output execution_analysis.csv

# 4. Compare algorithms
python -m execution.compare \
    --reports var/backtest/executions.ndjson \
    --benchmark vwap
```

---

## Dependencies Summary

```
Phase 7 (Research API) ✅
    └─> Phase 8.0 (Execution Foundations) — BusProto, BaseExecutor, Sync/Async adapters
            └─> 8.1 (Execution Contracts) — ExecutionAlgorithm, ExecutionSlice, ExecutionReport
                    └─> 8.2 (TWAP) — Time-Weighted Average Price
                            └─> 8.3 (VWAP) — Volume-Weighted Average Price
                                    └─> 8.4 (Iceberg) — Hidden order execution
                                            └─> 8.5 (POV) — Percentage of Volume
                                                    └─> 8.6 (Slippage Model) — Linear/Square-root models
                                                            └─> 8.7 (Execution Simulator) — Backtest integration
                                                                    └─> 8.8 (Smart Router) — Algorithm selection
                                                                            └─> 8.9 (Performance Metrics) — Execution quality tracking
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---

## Phase 9 — Metrics & Telemetry 📋

**Purpose:** Implement comprehensive observability with Prometheus metrics, Grafana dashboards, and real-time performance tracking.

**Current Status:** Phase 8 complete — Execution Layer fully operational
**Next Phase:** Phase 10 — Live Trade Controller

---

### Phase 9.0 — Metrics Contracts 📋
**Status:** Planned
**Dependencies:** 8.9 (Execution Performance Metrics)
**Task:** Define telemetry-specific contracts and metric types

**Contracts:**
```python
@dataclass(frozen=True)
class MetricSnapshot:
    """Single metric measurement."""
    name: str
    value: float
    timestamp_ns: int
    labels: dict[str, str]  # e.g., {"strategy_id": "twap_v1", "symbol": "ATOM/USDT"}
    metric_type: Literal["counter", "gauge", "histogram", "summary"]

@dataclass(frozen=True)
class StrategyMetrics:
    """Strategy-level performance metrics."""
    strategy_id: str
    timestamp_ns: int
    active_positions: int
    total_pnl: float
    daily_pnl: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown_pct: float
    orders_sent: int
    orders_filled: int
    orders_rejected: int

@dataclass(frozen=True)
class SystemMetrics:
    """System-level health metrics."""
    timestamp_ns: int
    bus_messages_sent: int
    bus_messages_received: int
    journal_writes: int
    journal_bytes: int
    active_subscriptions: int
    event_loop_lag_ms: float
    memory_usage_mb: float
```

**Files:**
- `telemetry/contracts.py` (80 LOC)
- `tests/test_telemetry_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Metric types follow Prometheus conventions
- Serializable to/from dict
- Labels support cardinality limits (warn if >100 unique combos)
- `make fmt lint type test` green

---

### Phase 9.1 — Prometheus Metrics Exporter 📋
**Status:** Planned
**Dependencies:** 9.0 (Metrics Contracts)
**Task:** Implement Prometheus-compatible metrics HTTP endpoint

**Behavior:**
- Expose metrics at `/metrics` endpoint (HTTP server on configurable port)
- Support standard Prometheus metric types: Counter, Gauge, Histogram, Summary
- Aggregate metrics from all services via Redis pub/sub
- Follow Prometheus naming conventions (snake_case, `_total` suffix for counters)
- Include help text and type hints in exposition format
- Support metric labels with cardinality protection

**API:**
```python
class PrometheusExporter:
    def __init__(
        self,
        bus: BusProto,
        port: int = 9090,
        bind_host: str = "127.0.0.1",  # Localhost-only by default
        registry: MetricRegistry | None = None
    ): ...

    async def start(self) -> None:
        """Start HTTP server for /metrics endpoint.

        Security:
            - Binds to localhost (127.0.0.1) by default
            - For production with Prometheus scraper on different host, explicitly set bind_host
            - Optional: Require Bearer token via env var NJORD_METRICS_TOKEN
        """
        pass

    async def collect_metrics(self) -> str:
        """Collect all metrics and format for Prometheus.

        Returns:
            Metrics in Prometheus exposition format
        """
        pass

    def register_counter(
        self,
        name: str,
        help_text: str,
        labels: list[str] | None = None
    ) -> Counter:
        """Register a counter metric."""
        pass

    def register_gauge(
        self,
        name: str,
        help_text: str,
        labels: list[str] | None = None
    ) -> Gauge:
        """Register a gauge metric."""
        pass

    def register_histogram(
        self,
        name: str,
        help_text: str,
        buckets: list[float],
        labels: list[str] | None = None
    ) -> Histogram:
        """Register a histogram metric."""
        pass
```

**Standard Metrics:**
```
# Counters
njord_orders_total{strategy_id, symbol, side}
njord_fills_total{strategy_id, symbol, side}
njord_risk_rejections_total{reason}
njord_bus_messages_total{topic, direction}

# Gauges
njord_active_positions{strategy_id, symbol}
njord_portfolio_equity_usd{portfolio_id}
njord_strategy_pnl_usd{strategy_id}
njord_event_loop_lag_seconds

# Histograms
njord_fill_latency_seconds{strategy_id}
njord_order_size_usd{strategy_id, symbol}
njord_execution_slippage_bps{algo_type}
```

**Files:**
- `telemetry/prometheus.py` (250 LOC)
- `telemetry/registry.py` (100 LOC for metric storage)
- `tests/test_prometheus_exporter.py`

**Acceptance:**
- HTTP endpoint serves metrics on `/metrics`
- **Security: Binds to localhost (127.0.0.1) by default** (prevents public exposure)
- **Security: Optional Bearer token auth via NJORD_METRICS_TOKEN env var**
- Exposition format valid (Prometheus scraper compatible)
- Counter increments persisted across scrapes
- Gauge updates reflect latest values
- Histogram buckets correctly categorize observations
- Cardinality protection warns/rejects high-cardinality labels
- Test includes scraping simulation (with/without auth token)
- `make fmt lint type test` green

---

### Phase 9.2 — Service Instrumentation 📋
**Status:** Planned
**Dependencies:** 9.1 (Prometheus Metrics Exporter)
**Task:** Instrument core services with metrics collection

**Behavior:**
- Add metrics collection to risk_engine, paper_trader, broker, strategy_runner
- Emit metrics to Redis topic `telemetry.metrics`
- Prometheus exporter subscribes and aggregates
- Use decorators for common patterns (timing, counting)
- **Production gating: Check env var NJORD_ENABLE_METRICS=1 before emitting** (disabled in tests)
- **Fallback: If Redis/bus unavailable, log metrics locally** (no service failure)
- Minimal performance overhead (<1% latency increase)

**Instrumentation Points:**

**Risk Engine:**
```python
# Counters
- njord_intents_received_total
- njord_intents_allowed_total
- njord_intents_denied_total{reason}
- njord_killswitch_trips_total

# Histograms
- njord_risk_check_duration_seconds
```

**Paper Trader / Broker:**
```python
# Counters
- njord_orders_placed_total{venue}
- njord_fills_generated_total{venue}

# Gauges
- njord_open_orders{symbol}
- njord_position_size{strategy_id, symbol}

# Histograms
- njord_fill_price_deviation_bps
```

**Strategy Runner:**
```python
# Counters
- njord_signals_generated_total{strategy_id}
- njord_strategy_errors_total{strategy_id}

# Histograms
- njord_signal_generation_duration_seconds{strategy_id}
```

**Helper Decorators:**
```python
@count_calls(metric_name="njord_function_calls_total")
async def handle_intent(self, intent: OrderIntent) -> None:
    ...

@measure_duration(metric_name="njord_processing_duration_seconds")
async def process_event(self, event: TradeEvent) -> None:
    ...
```

**Files:**
- `telemetry/decorators.py` (80 LOC)
- Update `apps/risk_engine/main.py` (+50 LOC)
- Update `apps/paper_trader/main.py` (+50 LOC)
- Update `apps/broker_binanceus/main.py` (+50 LOC)
- Update `apps/strategy_runner/main.py` (+50 LOC)
- `tests/test_service_instrumentation.py`

**Acceptance:**
- All core services emit metrics to `telemetry.metrics` topic
- **Metrics emission gated by NJORD_ENABLE_METRICS=1 env var** (disabled by default in tests)
- **Graceful degradation: Metrics failures don't crash services** (log + continue)
- Decorators correctly measure duration and count calls
- Metrics include appropriate labels (strategy_id, symbol, etc.)
- Performance overhead <1% (benchmark test)
- Test verifies metrics disabled when NJORD_ENABLE_METRICS unset
- Test verifies service continues if bus unavailable (fallback to local logging)
- `make fmt lint type test` green

---

### Phase 9.3 — Grafana Dashboard Configs 📋
**Status:** Planned
**Dependencies:** 9.2 (Service Instrumentation)
**Task:** Create Grafana dashboard JSON configs for visualization

**Deliverables:**

**1. System Health Dashboard**
- Event loop lag over time
- Bus message throughput (messages/sec)
- Memory usage per service
- Journal write rates
- Active subscriptions count

**2. Trading Activity Dashboard**
- Orders sent/filled/rejected (rate and count)
- Fill latency distribution (P50, P95, P99)
- Position sizes by strategy
- Daily PnL by strategy (bar chart)
- Risk rejection reasons (pie chart)

**3. Strategy Performance Dashboard**
- Equity curves (multi-strategy overlay)
- Sharpe ratio comparison (bar chart)
- Win rate by strategy (gauge)
- Max drawdown by strategy (gauge)
- Signal generation rate

**4. Execution Quality Dashboard**
- Execution slippage by algorithm (TWAP/VWAP/Iceberg/POV)
- Implementation shortfall distribution
- Venue fill rates
- Order size distribution (histogram)

**Dashboard Features:**
- Variable selectors: strategy_id, symbol, time range
- Alerts on critical thresholds (drawdown >10%, lag >100ms)
- Drill-down from summary to detail views
- Auto-refresh every 5 seconds

**Files:**
- `deploy/grafana/system_health.json` (dashboard config)
- `deploy/grafana/trading_activity.json`
- `deploy/grafana/strategy_performance.json`
- `deploy/grafana/execution_quality.json`
- `deploy/grafana/datasources.yaml` (Prometheus config)
- `deploy/grafana/README.md` (import instructions)
- `tests/test_dashboard_validity.py` (JSON schema validation)

**Acceptance:**
- Dashboard JSONs valid (Grafana import succeeds)
- All panels query correct Prometheus metrics
- Variable selectors work (tested with mock data)
- Alerts configured with reasonable thresholds
- README includes import and setup instructions
- Test validates JSON structure
- `make fmt lint type test` green

---

### Phase 9.4 — Metric Aggregation Service 📋
**Status:** Planned
**Dependencies:** 9.3 (Grafana Dashboard Configs)
**Task:** Centralized service for metric aggregation and persistence

**Behavior:**
- Subscribe to `telemetry.metrics` topic
- Aggregate metrics in memory (rolling windows)
- Persist aggregated metrics to journal
- **Publish aggregated rollups to shared MetricRegistry** (consumed by PrometheusExporter)
- **Integration: PrometheusExporter reads from same MetricRegistry instance** (passed in constructor)
- **Flow: Raw metrics → Aggregator → Registry → Exporter → Prometheus scraper**
- Support metric downsampling (1m → 5m → 1h → 1d)
- Handle late-arriving metrics (grace period)

**API:**
```python
class MetricAggregator:
    def __init__(
        self,
        bus: BusProto,
        journal_dir: Path,
        registry: MetricRegistry,  # Shared with PrometheusExporter
        retention_hours: int = 168  # 7 days
    ): ...

    async def run(self) -> None:
        """Main aggregation loop."""
        pass

    async def aggregate_metrics(
        self,
        snapshot: MetricSnapshot
    ) -> None:
        """Aggregate incoming metric snapshot."""
        pass

    def downsample_to_interval(
        self,
        metrics: list[MetricSnapshot],
        interval_seconds: int
    ) -> list[MetricSnapshot]:
        """Downsample metrics to interval (avg for gauges, sum for counters)."""
        pass

    def flush_to_journal(self) -> None:
        """Persist aggregated metrics to journal."""
        pass

    def publish_to_registry(self, metrics: list[MetricSnapshot]) -> None:
        """Publish aggregated metrics to shared MetricRegistry.

        CRITICAL: This is how PrometheusExporter accesses aggregated data.
        Both aggregator and exporter must share the same MetricRegistry instance.
        """
        pass
```

**Aggregation Rules:**
- Counters: Sum over interval
- Gauges: Average over interval (or last value)
- Histograms: Merge buckets
- Summary: Combine percentiles

**Files:**
- `apps/metric_aggregator/main.py` (200 LOC)
- `telemetry/aggregation.py` (150 LOC)
- `tests/test_metric_aggregator.py`

**Acceptance:**
- Subscribes to `telemetry.metrics` and aggregates
- **CRITICAL: Publishes aggregated metrics to shared MetricRegistry** (PrometheusExporter integration)
- **Test verifies MetricRegistry contains aggregated rollups** (not just raw metrics)
- **Integration test: Aggregator + Exporter share same registry, exporter serves aggregated data**
- Downsampling produces correct values (sum for counters, avg for gauges)
- Journal persistence includes timestamp and labels
- Late metrics handled within grace period (5 minutes)
- Memory bounded (rolling window eviction)
- Test includes downsample validation
- `make fmt lint type test` green

---

### Phase 9.5 — Performance Attribution 📋
**Status:** Planned
**Dependencies:** 9.4 (Metric Aggregation Service)
**Task:** Attribute portfolio performance to individual strategies

**Behavior:**
- Track strategy contributions to portfolio PnL
- Calculate attribution metrics (absolute, relative, risk-adjusted)
- Identify performance drivers (alpha vs. beta)
- Compare strategy performance vs. benchmark
- Generate attribution reports

**API:**
```python
class PerformanceAttribution:
    def __init__(
        self,
        data_reader: DataReader,
        portfolio_id: str
    ): ...

    def calculate_attribution(
        self,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> AttributionReport:
        """Calculate performance attribution.

        Returns:
            Attribution report with strategy contributions
        """
        pass

    def attribute_pnl(
        self,
        portfolio_pnl: float,
        strategy_pnls: dict[str, float],
        strategy_weights: dict[str, float]
    ) -> dict[str, float]:
        """Attribute portfolio PnL to strategies.

        Returns:
            Dict mapping strategy_id to attributed PnL
        """
        pass

    def calculate_alpha_beta(
        self,
        strategy_returns: list[float],
        benchmark_returns: list[float]
    ) -> tuple[float, float]:
        """Calculate alpha and beta vs. benchmark.

        Returns:
            (alpha, beta) tuple
        """
        pass
```

**Attribution Methods:**
- Brinson attribution (allocation + selection effects)
- Factor-based attribution (decompose by risk factors)
- Risk-adjusted attribution (Sharpe/Sortino weighted)

**Files:**
- `telemetry/attribution.py` (200 LOC)
- `tests/test_performance_attribution.py`

**Acceptance:**
- PnL attribution matches portfolio total (sum test)
- Alpha/beta calculation matches manual computation
- Brinson attribution decomposes correctly
- Handles missing strategy data gracefully
- Test includes known attribution scenarios
- `make fmt lint type test` green

---

### Phase 9.6 — Real-Time Metrics Dashboard 📋
**Status:** Planned
**Dependencies:** 9.5 (Performance Attribution)
**Task:** Web-based real-time metrics dashboard (optional HTML/JS)

**Behavior:**
- Lightweight web dashboard served on HTTP port
- Auto-refresh metrics every 1 second (WebSocket or SSE)
- Display key metrics: PnL, positions, orders, risk status
- No external dependencies (embedded HTML/CSS/JS)
- Read-only view (no controls)

**API:**
```python
class MetricsDashboard:
    def __init__(
        self,
        bus: BusProto,
        port: int = 8080,
        bind_host: str = "127.0.0.1"  # Localhost-only by default
    ): ...

    async def start(self) -> None:
        """Start dashboard HTTP server.

        Security:
            - Binds to localhost (127.0.0.1) by default
            - For production access from other hosts, explicitly set bind_host
            - Optional: Require Bearer token via env var NJORD_DASHBOARD_TOKEN
        """
        pass

    async def stream_metrics(self) -> AsyncIterator[dict[str, Any]]:
        """Stream metrics updates via SSE."""
        pass

    def render_dashboard(self) -> str:
        """Render dashboard HTML."""
        pass
```

**Dashboard Sections:**
- Portfolio Summary (equity, daily PnL, positions count)
- Strategy Performance (Sharpe, win rate, PnL)
- Risk Status (kill-switch, caps utilization)
- Recent Activity (last 10 orders/fills)
- System Health (bus lag, memory usage)

**Files:**
- `apps/metrics_dashboard/main.py` (150 LOC)
- `apps/metrics_dashboard/templates/dashboard.html` (embedded)
- `tests/test_metrics_dashboard.py`

**Acceptance:**
- Dashboard accessible at `http://localhost:8080`
- **Security: Binds to localhost (127.0.0.1) by default** (prevents public exposure)
- **Security: Optional Bearer token auth via NJORD_DASHBOARD_TOKEN env var**
- Metrics update in real-time (1 sec refresh)
- All sections display correct data
- No external JS libraries (vanilla JS only)
- Mobile-responsive layout
- Test includes auth enforcement (valid/invalid token scenarios)
- `make fmt lint type test` green

---

### Phase 9.7 — Metric Alerts 📋
**Status:** Planned
**Dependencies:** 9.6 (Real-Time Metrics Dashboard)
**Task:** Alert system for metric threshold violations

**Behavior:**
- Define alert rules in YAML config
- Evaluate rules against incoming metrics
- Fire alerts when thresholds breached
- Support alert channels: log, Redis pub/sub, webhook (no Slack/email in phase 9)
- Deduplication (avoid alert spam)
- Auto-resolve when condition clears

**Alert Rules Config:**
```yaml
alerts:
  - name: high_drawdown
    metric: njord_strategy_drawdown_pct
    condition: "> 10.0"
    duration: 60  # seconds
    labels:
      severity: critical
    annotations:
      summary: "Strategy {{ $labels.strategy_id }} drawdown exceeded 10%"

  - name: event_loop_lag
    metric: njord_event_loop_lag_seconds
    condition: "> 0.1"
    duration: 30
    labels:
      severity: warning
```

**API:**
```python
class AlertManager:
    def __init__(
        self,
        bus: BusProto,
        rules_path: Path
    ): ...

    async def evaluate_rules(
        self,
        snapshot: MetricSnapshot
    ) -> list[Alert]:
        """Evaluate alert rules against metric.

        Returns:
            List of alerts fired
        """
        pass

    async def fire_alert(
        self,
        alert: Alert
    ) -> None:
        """Fire alert to configured channels."""
        pass

    def deduplicate_alert(
        self,
        alert: Alert
    ) -> bool:
        """Check if alert is duplicate (within time window).

        Returns:
            True if duplicate (skip), False if new
        """
        pass
```

**Files:**
- `telemetry/alerts.py` (180 LOC)
- `config/alerts.yaml` (example alert rules)
- `tests/test_alert_manager.py`

**Acceptance:**
- Alert rules loaded from YAML
- Threshold conditions evaluated correctly
- Duration requirement enforced (must breach for N seconds)
- Deduplication prevents spam (5 min window)
- Alerts published to `telemetry.alerts` topic
- Test includes threshold breach scenarios
- `make fmt lint type test` green

---

### Phase 9.8 — Metrics Retention & Cleanup 📋
**Status:** Planned
**Dependencies:** 9.7 (Metric Alerts)
**Task:** Implement metrics retention policy and cleanup

**Behavior:**
- Define retention periods per metric type
- Automatically delete old metrics from journal
- Downsample old metrics (1m → 5m → 1h → 1d)
- Compress old journals (gzip)
- Scheduled cleanup task (daily cron)

**Retention Policy:**
```yaml
retention:
  raw_metrics:
    - resolution: 1m
      retention_days: 7
    - resolution: 5m
      retention_days: 30
    - resolution: 1h
      retention_days: 180
    - resolution: 1d
      retention_days: 730  # 2 years

  cleanup_schedule: "0 2 * * *"  # 2 AM daily (cron format)
```

**Note:** Cron schedule validation uses simple regex (stdlib only, no croniter dependency).

**API:**
```python
class MetricsRetention:
    def __init__(
        self,
        journal_dir: Path,
        policy: RetentionPolicy
    ): ...

    def apply_retention(self) -> None:
        """Apply retention policy to metrics journals."""
        pass

    def downsample_metrics(
        self,
        source_resolution: str,
        target_resolution: str,
        cutoff_days: int
    ) -> None:
        """Downsample metrics older than cutoff."""
        pass

    def compress_journals(
        self,
        older_than_days: int
    ) -> None:
        """Compress journals older than threshold."""
        pass

    def delete_expired(
        self,
        older_than_days: int
    ) -> None:
        """Delete metrics older than retention period."""
        pass
```

**Files:**
- `telemetry/retention.py` (150 LOC)
- `scripts/metrics_cleanup.py` (CLI for manual cleanup)
- `tests/test_metrics_retention.py`

**Acceptance:**
- Retention policy correctly identifies old metrics
- Downsampling produces correct aggregates
- Compression reduces disk usage (test with sample data)
- Deletion removes only expired metrics
- Cron schedule parseable (basic format check: 5 space-separated fields, stdlib only, no external deps)
- Test includes retention boundary conditions
- `make fmt lint type test` green

---

### Phase 9.9 — Telemetry Documentation 📋
**Status:** Planned
**Dependencies:** 9.8 (Metrics Retention & Cleanup)
**Task:** Document telemetry system and operational procedures

**Deliverables:**

**1. Metrics Catalog**
- Complete list of all exposed metrics
- Metric types, labels, help text
- Example PromQL queries
- Alert rule examples

**2. Grafana Setup Guide**
- Prometheus installation and configuration
- Grafana installation and datasource setup
- Dashboard import instructions
- Alert channel configuration

**3. Operations Runbook**
- Starting/stopping telemetry services
- Troubleshooting common issues
- Metrics retention management
- Performance tuning (cardinality, scrape interval)

**4. API Documentation**
- MetricSnapshot, StrategyMetrics, SystemMetrics contracts
- PrometheusExporter usage
- Instrumentation decorator usage
- Custom metric registration

**Files:**
- `docs/telemetry/metrics_catalog.md`
- `docs/telemetry/grafana_setup.md`
- `docs/telemetry/operations_runbook.md`
- `docs/telemetry/api_reference.md`
- `tests/test_telemetry_docs.py` (validate links, code examples)

**Acceptance:**
- Metrics catalog complete (all metrics documented)
- Setup guide tested (fresh Grafana installation)
- Runbook covers common scenarios
- API docs include working code examples
- All markdown links valid
- Code examples in docs execute without errors
- `make fmt lint type test` green

---

**Phase 9 Acceptance Criteria:**
- [ ] All 10 tasks completed (9.0-9.9)
- [ ] `make fmt lint type test` green
- [ ] Prometheus exporter serves metrics on `/metrics` endpoint
- [ ] All core services instrumented with metrics
- [ ] Grafana dashboards import and display data
- [ ] Metric aggregation service running and persisting data
- [ ] Performance attribution calculates correctly
- [ ] Real-time dashboard accessible and updating
- [ ] Alert rules fire on threshold violations
- [ ] Metrics retention policy applied automatically
- [ ] Documentation complete and verified
- [ ] No runtime dependencies beyond existing stack (Prometheus/Grafana deployment-only)
- [ ] Metric cardinality bounded (warn at 100 unique label combinations)
- [ ] Performance overhead <1% (benchmark test)

---

## Integration with Existing System

### Telemetry Flow
```
Services (risk_engine, paper_trader, broker, strategies)
    ↓
Emit MetricSnapshot to telemetry.metrics topic
    ↓
MetricAggregator (9.4) — Aggregate & Persist
    ↓
PrometheusExporter (9.1) — Serve /metrics endpoint
    ↓
Prometheus (external) — Scrape metrics
    ↓
Grafana (external) — Visualize dashboards
    ↓
AlertManager (9.7) — Fire alerts on thresholds
    ↓
Operators — Monitor & respond
```

### Example Telemetry Session
```bash
# 1. Start metric aggregator
python -m apps.metric_aggregator --config ./config/base.yaml

# 2. Start Prometheus exporter
python -m telemetry.prometheus --port 9090

# 3. Configure Prometheus to scrape
cat > prometheus.yml <<EOF
scrape_configs:
  - job_name: 'njord'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 5s
EOF

# 4. Start Prometheus
prometheus --config.file=prometheus.yml

# 5. Import Grafana dashboards
grafana-cli admin reset-admin-password admin
# Import deploy/grafana/*.json via UI

# 6. Start real-time dashboard (optional)
python -m apps.metrics_dashboard --port 8080

# 7. View metrics
curl http://localhost:9090/metrics
open http://localhost:3000  # Grafana
open http://localhost:8080  # Real-time dashboard
```

---

## Dependencies Summary

```
Phase 8 (Execution Layer) ✅
    └─> Phase 9.0 (Metrics Contracts)
            └─> 9.1 (Prometheus Exporter)
                    └─> 9.2 (Service Instrumentation)
                            └─> 9.3 (Grafana Dashboards)
                                    └─> 9.4 (Metric Aggregator)
                                            └─> 9.5 (Performance Attribution)
                                                    └─> 9.6 (Real-Time Dashboard)
                                                            └─> 9.7 (Metric Alerts)
                                                                    └─> 9.8 (Metrics Retention)
                                                                            └─> 9.9 (Telemetry Docs)
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---

## Phase 10 — Live Trade Controller 📋

**Purpose:** Implement unified CLI for managing all trading services with config hot-reload and session journaling.

**Current Status:** Phase 9 complete — Metrics & Telemetry fully operational
**Next Phase:** Phase 11 — Monitoring & Alerts

---

### Phase 10.0 — Controller Contracts 📋
**Status:** Planned
**Dependencies:** 9.9 (Telemetry Documentation)
**Task:** Define service control contracts and session tracking

**Contracts:**
```python
@dataclass(frozen=True)
class ServiceStatus:
    """Status of a single service."""
    service_name: str
    status: Literal["running", "stopped", "starting", "stopping", "error"]
    pid: int | None
    uptime_seconds: int
    last_error: str | None
    timestamp_ns: int

@dataclass(frozen=True)
class SessionSnapshot:
    """Trading session metadata."""
    session_id: str
    start_ts_ns: int
    end_ts_ns: int | None
    services: list[str]  # Service names in session
    config_hash: str  # SHA256 of config files
    status: Literal["active", "stopped", "error"]

@dataclass(frozen=True)
class ControlCommand:
    """Command to control services."""
    command: Literal["start", "stop", "restart", "reload", "status"]
    service_names: list[str]  # Empty list = all services
    session_id: str
    timestamp_ns: int
```

**Files:**
- `controller/contracts.py` (80 LOC)
- `tests/test_controller_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- ServiceStatus includes PID tracking
- SessionSnapshot tracks config hash for reload detection
- `make fmt lint type test` green

---

### Phase 10.1 — Service Registry 📋
**Status:** Planned
**Dependencies:** 10.0 (Controller Contracts)
**Task:** Implement service discovery and registration

**Behavior:**
- Auto-discover services in `apps/` directory
- Register service metadata (name, entry point, dependencies)
- Support service dependency ordering (start risk_engine before broker)
- Validate service existence before operations
- Support service groups (e.g., "live", "paper", "backtest")

**API:**
```python
class ServiceRegistry:
    def __init__(self, apps_dir: Path = Path("apps")): ...

    def discover_services(self) -> dict[str, ServiceMetadata]:
        """Discover all services in apps/ directory.

        Returns:
            Dict mapping service name to metadata
        """
        pass

    def get_service(self, name: str) -> ServiceMetadata:
        """Get service metadata by name.

        Raises:
            KeyError: If service not found
        """
        pass

    def get_start_order(
        self,
        service_names: list[str]
    ) -> list[str]:
        """Get topologically sorted start order based on dependencies.

        Returns:
            List of service names in start order
        """
        pass

    def get_service_group(
        self,
        group: Literal["live", "paper", "backtest", "all"]
    ) -> list[str]:
        """Get service names in group.

        Returns:
            List of service names
        """
        pass
```

**Service Groups:**
```yaml
groups:
  live:
    - md_ingest
    - risk_engine
    - broker_binanceus
    - portfolio_manager
    - metric_aggregator

  paper:
    - md_ingest
    - risk_engine
    - paper_trader
    - portfolio_manager
    - metric_aggregator

  backtest:
    - []  # No persistent services for backtest
```

**Files:**
- `controller/registry.py` (150 LOC)
- `controller/metadata.py` (ServiceMetadata dataclass, 50 LOC)
- `tests/test_service_registry.py`

**Acceptance:**
- Discovers all services in apps/ directory
- Correctly orders services by dependencies
- Validates service existence
- Service groups defined and retrievable
- Handles missing services gracefully (KeyError)
- `make fmt lint type test` green

---

### Phase 10.2 — Process Manager 📋
**Status:** Planned
**Dependencies:** 10.1 (Service Registry)
**Task:** Manage service process lifecycle (start/stop/restart)

**Behavior:**
- Start services as background processes
- **Safety: Check kill-switch before starting live services** (respect Phase 2 protections)
- **Safety: Require NJORD_ENABLE_LIVE=1 env var for live broker/trading services**
- Track PIDs and monitor process health
- Stop services gracefully (SIGTERM, then SIGKILL after timeout)
- Restart crashed services (optional auto-restart)
- Capture stdout/stderr to log files
- Environment variable injection

**API:**
```python
class ProcessManager:
    def __init__(
        self,
        registry: ServiceRegistry,
        log_dir: Path = Path("var/log/njord")
    ): ...

    async def start_service(
        self,
        service_name: str,
        config_root: Path = Path(".")
    ) -> ServiceStatus:
        """Start a service process.

        Returns:
            ServiceStatus with PID and status
        """
        pass

    async def stop_service(
        self,
        service_name: str,
        timeout_seconds: int = 10
    ) -> ServiceStatus:
        """Stop a service gracefully.

        Args:
            timeout_seconds: Wait for SIGTERM, then SIGKILL

        Returns:
            ServiceStatus after stopping
        """
        pass

    async def restart_service(
        self,
        service_name: str
    ) -> ServiceStatus:
        """Restart a service (stop + start).

        Returns:
            ServiceStatus after restart
        """
        pass

    def get_status(
        self,
        service_name: str
    ) -> ServiceStatus:
        """Get current service status.

        Returns:
            ServiceStatus with PID, uptime, status
        """
        pass

    async def monitor_health(
        self,
        service_name: str,
        interval_seconds: int = 5
    ) -> AsyncIterator[ServiceStatus]:
        """Monitor service health continuously.

        Yields:
            ServiceStatus updates
        """
        pass
```

**Files:**
- `controller/process.py` (250 LOC)
- `tests/test_process_manager.py`

**Acceptance:**
- Starts services as background processes
- **Safety: Checks kill-switch state before starting live services** (Phase 2 integration)
- **Safety: Validates NJORD_ENABLE_LIVE=1 env var for live broker** (prevents accidental live trading)
- Tracks PIDs correctly
- Stops services gracefully (SIGTERM before SIGKILL)
- Captures stdout/stderr to log files
- Monitors process health (detects crashes)
- Timeout enforcement on stop operations
- Test includes process lifecycle (start/stop/restart)
- Test includes kill-switch enforcement (refuses to start if tripped)
- `make fmt lint type test` green

---

### Phase 10.3 — Config Hot-Reload 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager)
**Task:** Implement configuration hot-reload without service restart

**Behavior:**
- Watch config files for changes
  - **Use inotify if available (Linux), otherwise fall back to polling every 5 seconds**
  - **Cross-platform: Detect platform and use appropriate method**
- Compute config hash (SHA256) for change detection
- Send reload signal to services (SIGHUP or Redis message)
- Services reload config on signal (no restart)
- Validate config before reload (reject invalid changes)
- Journal config changes with timestamps

**API:**
```python
class ConfigReloader:
    def __init__(
        self,
        bus: BusProto,
        config_root: Path = Path(".")
    ): ...

    async def watch_config(self) -> None:
        """Watch config files for changes."""
        pass

    def compute_config_hash(
        self,
        config_files: list[Path]
    ) -> str:
        """Compute SHA256 hash of config files.

        Returns:
            Hex-encoded SHA256 hash
        """
        pass

    async def reload_service_config(
        self,
        service_name: str
    ) -> bool:
        """Trigger config reload for service.

        Returns:
            True if reload successful
        """
        pass

    def validate_config(
        self,
        config_path: Path
    ) -> tuple[bool, str | None]:
        """Validate config file before reload.

        Returns:
            (valid, error_message)
        """
        pass
```

**Reload Mechanism:**
```python
# Option 1: SIGHUP signal
os.kill(pid, signal.SIGHUP)

# Option 2: Redis pub/sub (preferred for cross-host)
await bus.publish_json("controller.reload", {"service": service_name})

# Services listen for reload:
async for msg in bus.subscribe("controller.reload"):
    if msg["service"] == self.service_name:
        self.config = load_config()
        logger.info("config_reloaded")
```

**Files:**
- `controller/reload.py` (180 LOC)
- Update `apps/*/main.py` to handle reload signal (+20 LOC each)
- `tests/test_config_reload.py`

**Acceptance:**
- Detects config file changes (inotify on Linux, polling fallback for cross-platform)
- **Fallback mechanism tested: works on systems without inotify**
- Computes config hash correctly (SHA256)
- Sends reload signal to services (Redis pub/sub preferred)
- Services reload config without restart
- Config validation prevents invalid reloads
- Config changes journaled with timestamps
- Test includes reload simulation
- Test includes polling fallback path
- `make fmt lint type test` green

---

### Phase 10.4 — Session Manager 📋
**Status:** Planned
**Dependencies:** 10.3 (Config Hot-Reload)
**Task:** Track trading sessions and journal lifecycle events

**Behavior:**
- Create session on controller start
- Assign unique session_id (UUID)
- Journal session events (start, stop, config_reload, error)
- Track session metadata (config hash, services, uptime)
- Persist sessions to journal for audit
- Support session queries (current, historical)

**API:**
```python
class SessionManager:
    def __init__(
        self,
        journal_dir: Path = Path("var/log/njord")
    ): ...

    def create_session(
        self,
        services: list[str],
        config_hash: str
    ) -> SessionSnapshot:
        """Create new trading session.

        Returns:
            SessionSnapshot with session_id
        """
        pass

    def end_session(
        self,
        session_id: str
    ) -> SessionSnapshot:
        """End trading session.

        Returns:
            SessionSnapshot with end_ts_ns
        """
        pass

    def get_current_session(self) -> SessionSnapshot | None:
        """Get current active session.

        Returns:
            SessionSnapshot or None if no active session
        """
        pass

    def get_session_history(
        self,
        limit: int = 10
    ) -> list[SessionSnapshot]:
        """Get recent session history.

        Returns:
            List of SessionSnapshots (newest first)
        """
        pass

    def journal_event(
        self,
        session_id: str,
        event_type: str,
        details: dict[str, Any]
    ) -> None:
        """Journal session lifecycle event."""
        pass
```

**Session Journal Format (NDJSON):**
```json
{"session_id":"a1b2c3","event":"session_start","ts_ns":1234567890,"services":["risk_engine","paper_trader"],"config_hash":"abc123"}
{"session_id":"a1b2c3","event":"config_reload","ts_ns":1234567900,"config_hash":"def456"}
{"session_id":"a1b2c3","event":"service_crashed","ts_ns":1234567910,"service":"paper_trader","error":"connection lost"}
{"session_id":"a1b2c3","event":"session_end","ts_ns":1234567920}
```

**Files:**
- `controller/session.py` (150 LOC)
- `tests/test_session_manager.py`

**Acceptance:**
- Creates unique session IDs (UUID)
- Journals session lifecycle events (NDJSON)
- Tracks config hash for each session
- Retrieves current and historical sessions
- Session end timestamp recorded correctly
- Test includes session lifecycle (create/end/query)
- `make fmt lint type test` green

---

### Phase 10.5 — Log Aggregation 📋
**Status:** Planned
**Dependencies:** 10.4 (Session Manager)
**Task:** Aggregate and tail logs from multiple services

**Behavior:**
- Read logs from all service log files
- Support log tailing (--follow)
- Filter logs by service, level, time range
- Merge logs by timestamp (chronological order)
- Colorize by service/level
- Support log search (grep-like)

**API:**
```python
class LogAggregator:
    def __init__(
        self,
        log_dir: Path = Path("var/log/njord")
    ): ...

    def read_logs(
        self,
        service_names: list[str] | None = None,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None,
        level: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Read logs with filters.

        Returns:
            List of log entries (NDJSON parsed)
        """
        pass

    async def tail_logs(
        self,
        service_names: list[str] | None = None,
        level: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Tail logs continuously.

        Yields:
            Log entries as they arrive
        """
        pass

    def search_logs(
        self,
        pattern: str,
        service_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Search logs by pattern.

        Returns:
            Matching log entries
        """
        pass

    def merge_by_timestamp(
        self,
        log_entries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge and sort logs by timestamp.

        Returns:
            Chronologically ordered log entries
        """
        pass
```

**Files:**
- `controller/logs.py` (200 LOC)
- `tests/test_log_aggregator.py`

**Acceptance:**
- Reads logs from service log files (NDJSON)
- Merges logs by timestamp (chronological)
- Tail mode works (--follow)
- Filters by service, level, time range
- Search functionality works (regex)
- Colorized output by service/level (TTY detection)
- Test includes log aggregation scenarios
- `make fmt lint type test` green

---

### Phase 10.6 — CLI Framework 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager), 10.3 (Config Hot-Reload), 10.4 (Session Manager), 10.5 (Log Aggregation)
**Task:** Implement `njord-ctl` unified CLI tool

**Behavior:**
- Single entrypoint: `njord-ctl <command> [options]`
- Commands: start, stop, restart, reload, status, logs, session
- Support service selection (--service, --group, --all)
- Colorized output (optional, detect TTY)
- JSON output mode (--json)
- Dry-run mode (--dry-run)

**CLI Commands:**
```bash
# Start services
njord-ctl start --group live
njord-ctl start --service risk_engine,paper_trader
njord-ctl start --all

# Stop services
njord-ctl stop --group live
njord-ctl stop --service risk_engine
njord-ctl stop --all

# Restart services
njord-ctl restart --service paper_trader

# Reload config (no restart)
njord-ctl reload --all

# Check status
njord-ctl status
njord-ctl status --service risk_engine --json

# View logs
njord-ctl logs --service risk_engine --follow --lines 100

# Session management
njord-ctl session current
njord-ctl session history --limit 10
```

**API:**
```python
class NjordCLI:
    def __init__(
        self,
        config_root: Path = Path(".")
    ): ...

    def build_parser(self) -> argparse.ArgumentParser:
        """Build argument parser with all commands."""
        pass

    async def cmd_start(self, args: argparse.Namespace) -> int:
        """Handle start command."""
        pass

    async def cmd_stop(self, args: argparse.Namespace) -> int:
        """Handle stop command."""
        pass

    async def cmd_status(self, args: argparse.Namespace) -> int:
        """Handle status command."""
        pass

    async def cmd_reload(self, args: argparse.Namespace) -> int:
        """Handle reload command."""
        pass

    async def cmd_logs(self, args: argparse.Namespace) -> int:
        """Handle logs command."""
        pass

    async def cmd_session(self, args: argparse.Namespace) -> int:
        """Handle session command."""
        pass

    def format_output(
        self,
        data: Any,
        json_mode: bool = False
    ) -> str:
        """Format output (JSON or human-readable)."""
        pass
```

**Files:**
- `scripts/njord_ctl.py` (300 LOC)
- `controller/cli.py` (CLI helper utilities, 100 LOC)
- `tests/test_njord_ctl.py`

**Acceptance:**
- All commands implemented (start/stop/restart/reload/status/logs/session)
- Service selection works (--service, --group, --all)
- JSON output mode functional (--json)
- Colorized output when TTY detected
- Dry-run mode shows actions without executing (--dry-run)
- Error handling with clear messages
- Logs command integrates with LogAggregator (10.5)
- Test includes all CLI commands
- `make fmt lint type test` green

---

### Phase 10.7 — Service Health Checks 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager), 10.6 (CLI Framework)
**Task:** Implement health check probes for services

**Behavior:**
- Define health check endpoints per service
- Support HTTP health checks (GET /health)
- Support Redis ping checks
- Aggregate health status across services
- Auto-restart unhealthy services (optional)
- Expose overall system health

**API:**
```python
class HealthChecker:
    def __init__(
        self,
        process_manager: ProcessManager,
        bus: BusProto
    ): ...

    async def check_service_health(
        self,
        service_name: str
    ) -> tuple[bool, str]:
        """Check service health.

        Returns:
            (healthy, status_message)
        """
        pass

    async def check_http_endpoint(
        self,
        url: str,
        timeout_seconds: int = 5
    ) -> bool:
        """Check HTTP health endpoint.

        Returns:
            True if endpoint returns 200
        """
        pass

    async def check_redis_connectivity(
        self,
        redis_url: str
    ) -> bool:
        """Check Redis connectivity.

        Returns:
            True if Redis ping succeeds
        """
        pass

    async def monitor_all_services(
        self,
        interval_seconds: int = 30
    ) -> AsyncIterator[dict[str, bool]]:
        """Monitor all services continuously.

        Yields:
            Dict mapping service name to health status
        """
        pass
```

**Health Check Definitions:**
```yaml
health_checks:
  risk_engine:
    type: redis
    interval: 30

  paper_trader:
    type: redis
    interval: 30

  metric_aggregator:
    type: http
    url: http://localhost:9090/health
    interval: 30

  metrics_dashboard:
    type: http
    url: http://localhost:8080/health
    interval: 60
```

**Files:**
- `controller/health.py` (180 LOC)
- `config/health_checks.yaml` (health check definitions)
- Update services with `/health` endpoints (+20 LOC each)
- `tests/test_health_checker.py`

**Acceptance:**
- HTTP health checks functional (GET /health → 200)
- Redis connectivity checks functional (ping)
- Aggregates health status across services
- Monitoring loop runs continuously
- Auto-restart on unhealthy service (configurable)
- Test includes health check scenarios (healthy/unhealthy)
- `make fmt lint type test` green

---

### Phase 10.8 — Controller Service 📋
**Status:** Planned
**Dependencies:** 10.2 (Process Manager), 10.4 (Session Manager), 10.7 (Service Health Checks)
**Task:** Long-running controller daemon for session management

**Behavior:**
- Run as persistent daemon (background process)
- Manage session lifecycle automatically
- Monitor service health continuously
- Auto-restart crashed services (configurable)
- Expose control API (HTTP or Unix socket)
- Journal controller events

**API:**
```python
class ControllerDaemon:
    def __init__(
        self,
        config: Config,
        session_manager: SessionManager,
        process_manager: ProcessManager,
        health_checker: HealthChecker
    ): ...

    async def start(self) -> None:
        """Start controller daemon."""
        pass

    async def run(self) -> None:
        """Main daemon loop."""
        pass

    async def handle_service_crash(
        self,
        service_name: str
    ) -> None:
        """Handle service crash (auto-restart if enabled)."""
        pass

    async def expose_control_api(
        self,
        port: int = 9091,
        bind_host: str = "127.0.0.1"
    ) -> None:
        """Expose HTTP control API.

        Security:
            - Default bind to localhost only (127.0.0.1)
            - Require Bearer token auth for all endpoints
            - Token from env var NJORD_CONTROLLER_TOKEN
            - Reject requests without valid token (401 Unauthorized)

        Endpoints:
            GET /status (requires auth)
            POST /start (requires auth)
            POST /stop (requires auth)
            POST /reload (requires auth)
        """
        pass
```

**Daemon Features:**
- Runs in background (daemonize or systemd)
- Monitors all services (health checks)
- Auto-restart on crash (configurable per service)
- **Exposes HTTP API for remote control (localhost-only by default, token auth required)**
- **Security: Bearer token authentication (NJORD_CONTROLLER_TOKEN env var)**
- Graceful shutdown (SIGTERM handler)

**Files:**
- `apps/controller/main.py` (200 LOC)
- `controller/daemon.py` (150 LOC)
- `tests/test_controller_daemon.py`

**Acceptance:**
- Daemon runs in background
- Monitors service health continuously
- Auto-restarts crashed services (configurable)
- HTTP control API functional (start/stop/status/reload)
- **Security: API binds to localhost only by default** (127.0.0.1)
- **Security: Bearer token authentication enforced** (NJORD_CONTROLLER_TOKEN)
- **Security: Rejects requests without valid token (401 Unauthorized)**
- Graceful shutdown on SIGTERM
- Journals controller events (NDJSON)
- Test includes daemon lifecycle
- Test includes auth enforcement (valid/invalid token scenarios)
- `make fmt lint type test` green

---

### Phase 10.9 — Controller Documentation 📋
**Status:** Planned
**Dependencies:** 10.8 (Controller Service)
**Task:** Document controller system and operational procedures

**Deliverables:**

**1. CLI Reference**
- Complete command documentation (`njord-ctl --help` output)
- Command examples for common tasks
- Service group definitions
- Configuration options

**2. Session Management Guide**
- Session lifecycle explanation
- Session journaling format
- Session queries and history
- Config hot-reload procedures

**3. Operations Runbook**
- Starting/stopping services
- Monitoring service health
- Handling crashed services
- Log aggregation and search
- Troubleshooting common issues

**4. API Documentation**
- Controller HTTP API endpoints
- Health check probe definitions
- Service registry format
- Process manager usage

**Files:**
- `docs/controller/cli_reference.md`
- `docs/controller/session_management.md`
- `docs/controller/operations_runbook.md`
- `docs/controller/api_reference.md`
- `tests/test_controller_docs.py` (validate links, code examples)

**Acceptance:**
- CLI reference complete (all commands documented)
- Session management guide tested (follow procedures)
- Operations runbook covers common scenarios
- API docs include working code examples
- All markdown links valid
- Code examples in docs execute without errors
- `make fmt lint type test` green

---

**Phase 10 Acceptance Criteria:**
- [ ] All 10 tasks completed (10.0-10.9)
- [ ] `make fmt lint type test` green
- [ ] `njord-ctl` CLI functional with all commands
- [ ] Services start/stop/restart via controller
- [ ] Config hot-reload works without service restart
- [ ] Session journaling tracks all lifecycle events
- [ ] Health checks monitor all services
- [ ] Log aggregation merges and tails logs correctly
- [ ] Controller daemon runs as persistent service
- [ ] Documentation complete and verified
- [ ] No new runtime dependencies (stdlib + existing stack only)
- [ ] All timestamps use `*_ns` suffix
- [ ] Graceful shutdown on SIGTERM (all services)

---

## Integration with Existing System

### Controller Flow
```
njord-ctl start --group live
    ↓
ServiceRegistry → get_service_group("live")
    ↓
ProcessManager → start_service(each service)
    ↓
SessionManager → create_session(services, config_hash)
    ↓
HealthChecker → monitor_all_services()
    ↓
Services Running (risk_engine, broker, etc.)
    ↓
ConfigReloader → watch_config() → reload on change
    ↓
SessionManager → journal_event("config_reload")
    ↓
njord-ctl stop --all
    ↓
ProcessManager → stop_service(each service, SIGTERM)
    ↓
SessionManager → end_session(session_id)
```

### Example Controller Session
```bash
# 1. Start controller daemon
njord-ctl daemon start

# 2. Start live trading services
njord-ctl start --group live

# 3. Check status
njord-ctl status
# Output:
# SERVICE           STATUS    PID     UPTIME
# md_ingest         running   1234    00:15:32
# risk_engine       running   1235    00:15:31
# broker_binanceus  running   1236    00:15:30
# portfolio_manager running   1237    00:15:29
# metric_aggregator running   1238    00:15:28

# 4. Reload config (no restart)
njord-ctl reload --all

# 5. Tail logs
njord-ctl logs --service risk_engine --follow

# 6. Check session
njord-ctl session current
# Output:
# SESSION_ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
# STARTED:    2025-10-01 14:30:00 UTC
# UPTIME:     01:23:45
# SERVICES:   5 running
# CONFIG:     abc123def456 (no changes)

# 7. Stop all services
njord-ctl stop --all

# 8. Stop controller daemon
njord-ctl daemon stop
```

---

## Dependencies Summary

```
Phase 9 (Metrics & Telemetry) ✅
    └─> Phase 10.0 (Controller Contracts)
            └─> 10.1 (Service Registry)
                    └─> 10.2 (Process Manager) ━━━━┓
                            └─> 10.3 (Config Hot-Reload) ━━┓
                                    └─> 10.4 (Session Manager) ━┓
                                            └─> 10.5 (Log Aggregation) ━┓
                                                    │
                                                    └─> 10.6 (CLI Framework) ⭐
                                                            │  [Multi-deps: 10.2, 10.3, 10.4, 10.5]
                                                            │
                                                            └─> 10.7 (Service Health Checks)
                                                                    │  [Also depends: 10.2]
                                                                    │
                                                                    └─> 10.8 (Controller Service)
                                                                            │  [Also depends: 10.2, 10.4]
                                                                            │
                                                                            └─> 10.9 (Controller Docs)
```

**Dependency Notes:**
- **10.5 (Log Aggregation)** reordered before CLI to satisfy `logs` command dependency
- **10.6 (CLI Framework)** has explicit multi-dependencies on 10.2, 10.3, 10.4, 10.5
- **10.7 (Health Checks)** also depends on 10.2 (ProcessManager for monitoring)
- **10.8 (Controller Service)** also depends on 10.2 (ProcessManager), 10.4 (SessionManager)

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---

## Phase 11 — Monitoring & Alerts 📋

**Purpose:** Implement comprehensive alert system for operational events, risk violations, and performance anomalies.

**Current Status:** Phase 10 complete — Live Trade Controller fully operational
**Next Phase:** Phase 12 — Compliance & Audit

---

### Phase 11.0 — Alert Contracts 📋
**Status:** Planned
**Dependencies:** 10.9 (Controller Documentation)
**Task:** Define alert-specific contracts and notification types

**Contracts:**
```python
@dataclass(frozen=True)
class Alert:
    """Single alert event."""
    alert_id: str  # UUID
    timestamp_ns: int
    severity: Literal["info", "warning", "error", "critical"]
    category: Literal["system", "risk", "performance", "execution", "killswitch"]
    source: str  # Service name (risk_engine, paper_trader, etc.)
    title: str
    message: str
    labels: dict[str, str]  # e.g., {"strategy_id": "twap_v1", "symbol": "BTC/USDT"}
    annotations: dict[str, str]  # Additional context

@dataclass(frozen=True)
class AlertRule:
    """Alert rule definition."""
    rule_id: str
    name: str
    condition: str  # e.g., "drawdown_pct > 10.0"
    metric_name: str  # Metric to evaluate
    threshold: float
    duration_seconds: int  # How long condition must hold
    severity: Literal["info", "warning", "error", "critical"]
    channels: list[str]  # ["log", "redis", "webhook"]
    labels: dict[str, str]
    annotations: dict[str, str]
    enabled: bool

@dataclass(frozen=True)
class NotificationChannel:
    """Notification channel configuration."""
    channel_id: str
    channel_type: Literal["log", "redis", "webhook", "email", "slack"]
    config: dict[str, Any]  # Channel-specific config
    enabled: bool
    rate_limit_per_hour: int  # Max notifications per hour
```

**Files:**
- `alerts/contracts.py` (100 LOC)
- `tests/test_alert_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- Validation: severity/category enums valid, threshold > 0
- **NotificationChannel.rate_limit_per_hour enforced by AlertBus** (not individual channels)
- **Test verifies rate_limit_per_hour validation** (must be > 0)
- `make fmt lint type test` green

---

### Phase 11.1 — Alert Bus 📋
**Status:** Planned
**Dependencies:** 11.0 (Alert Contracts)
**Task:** Centralized alert routing and distribution

**Behavior:**
- Subscribe to alert sources (Redis topics, service logs, metric violations)
- Route alerts to configured channels based on severity/category
- Deduplication (suppress duplicate alerts within time window)
- Alert state tracking (active, resolved, acknowledged)
- Rate limiting per channel (prevent notification storms)
- Publish to Redis topic `alerts.fired` for persistence

**API:**
```python
class AlertBus:
    def __init__(
        self,
        bus: BusProto,
        channels: dict[str, NotificationChannel]
    ): ...

    async def publish_alert(self, alert: Alert) -> None:
        """Publish alert and route to channels.

        Behavior:
            - Check deduplication window (5 minutes by default)
            - Apply rate limits per channel
            - Route to channels matching severity threshold
            - Publish to alerts.fired topic for journaling
        """
        pass

    async def resolve_alert(self, alert_id: str) -> None:
        """Mark alert as resolved."""
        pass

    def should_suppress(
        self,
        alert: Alert,
        window_seconds: int = 300
    ) -> bool:
        """Check if alert should be suppressed (duplicate)."""
        pass

    async def route_to_channels(
        self,
        alert: Alert
    ) -> list[str]:
        """Determine which channels should receive alert.

        Returns:
            List of channel IDs that will receive alert
        """
        pass
```

**Deduplication Strategy:**
- Key: `(source, category, labels hash)`
- Window: 5 minutes (configurable)
- Store in Redis with TTL

**Files:**
- `alerts/bus.py` (200 LOC)
- `tests/test_alert_bus.py`

**Acceptance:**
- Publishes alerts to `alerts.fired` topic
- Deduplication prevents duplicate alerts within 5-minute window (Redis TTL-based)
- **Test verifies Redis TTL expiration for dedup keys** (key disappears after window)
- Rate limiting enforced per channel (max N/hour)
- **Test verifies rate limit blocks Nth+1 alert** (within same hour)
- **Test verifies rate limit resets after hour boundary**
- Alert routing based on severity thresholds
- **Test verifies severity filtering** (critical alert skips info-only channels)
- Test includes deduplication and rate limit scenarios
- `make fmt lint type test` green

---

### Phase 11.2 — Rule Engine 📋
**Status:** Planned
**Dependencies:** 11.1 (Alert Bus)
**Task:** Evaluate alert rules against metrics and events

**Behavior:**
- Load alert rules from YAML config (`config/alerts.yaml`)
- Subscribe to `telemetry.metrics` topic
- Evaluate rules against incoming metrics
- Track condition duration (must hold for N seconds)
- Fire alerts when thresholds breached for duration
- Auto-resolve when condition clears
- Support simple conditions: `>`, `<`, `>=`, `<=`, `==`, `!=`

**Alert Rules Config:**
```yaml
# config/alerts.yaml
rules:
  - rule_id: high_drawdown
    name: "High Strategy Drawdown"
    metric_name: njord_strategy_drawdown_pct
    condition: "> 10.0"
    duration_seconds: 60
    severity: critical
    channels: [log, redis, webhook]
    labels:
      category: performance
    annotations:
      summary: "Strategy {{ $labels.strategy_id }} drawdown exceeded 10%"
      runbook: "https://wiki.internal/runbooks/high-drawdown"

  - rule_id: killswitch_trip
    name: "Kill Switch Triggered"
    metric_name: njord_killswitch_trips_total
    condition: "> 0"
    duration_seconds: 1
    severity: critical
    channels: [log, redis, webhook]
    labels:
      category: killswitch
    annotations:
      summary: "Kill switch has been tripped"

  - rule_id: risk_rejection_rate
    name: "High Risk Rejection Rate"
    metric_name: njord_intents_denied_total
    condition: "> 100"
    duration_seconds: 300  # 5 minutes
    severity: warning
    channels: [log]
    labels:
      category: risk
```

**API:**
```python
class RuleEngine:
    def __init__(
        self,
        bus: BusProto,
        alert_bus: AlertBus,
        config_path: Path
    ): ...

    async def load_rules(self) -> None:
        """Load alert rules from YAML config."""
        pass

    async def evaluate_metric(
        self,
        snapshot: MetricSnapshot
    ) -> None:
        """Evaluate metric against all matching rules."""
        pass

    def check_condition(
        self,
        rule: AlertRule,
        value: float
    ) -> bool:
        """Check if metric value meets rule condition.

        Supports: >, <, >=, <=, ==, !=
        """
        pass

    async def track_duration(
        self,
        rule_id: str,
        breached: bool,
        timestamp_ns: int
    ) -> bool:
        """Track how long condition has held.

        Returns:
            True if duration threshold met (should fire alert)
        """
        pass

    def render_annotations(
        self,
        rule: AlertRule,
        labels: dict[str, str]
    ) -> dict[str, str]:
        """Render annotation templates with label substitution.

        Example: "{{ $labels.strategy_id }}" → "twap_v1"
        """
        pass
```

**Files:**
- `alerts/rules.py` (250 LOC)
- `tests/test_rule_engine.py`

**Acceptance:**
- Loads rules from `config/alerts.yaml`
- Evaluates conditions correctly (>, <, >=, <=, ==, !=)
- Duration tracking works (fires only after N seconds)
- Auto-resolves when condition clears
- Annotation template rendering works (label substitution)
- Test includes duration tracking and auto-resolve scenarios
- `make fmt lint type test` green

---

### Phase 11.3 — Log Notification Channel 📋
**Status:** Planned
**Dependencies:** 11.2 (Rule Engine)
**Task:** Log-based notification channel (always available)

**Behavior:**
- Write alerts to structured log (NDJSON)
- Separate alert log: `var/log/njord/alerts.ndjson`
- Include full alert context (severity, category, labels, annotations)
- No external dependencies (always works)
- Rotation handled externally (not inline)

**API:**
```python
class LogNotificationChannel:
    def __init__(
        self,
        log_path: Path = Path("var/log/njord/alerts.ndjson")
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Write alert to log file.

        Returns:
            True if successful, False if failed
        """
        pass

    def format_alert(self, alert: Alert) -> str:
        """Format alert as NDJSON line."""
        pass
```

**Files:**
- `alerts/channels/log.py` (60 LOC)
- `tests/test_log_channel.py`

**Acceptance:**
- Alerts written to `var/log/njord/alerts.ndjson`
- NDJSON format (one alert per line)
- Includes all alert fields (severity, category, labels, annotations)
- No external dependencies
- Test verifies alert persistence
- `make fmt lint type test` green

---

### Phase 11.4 — Redis Notification Channel 📋
**Status:** Planned
**Dependencies:** 11.3 (Log Notification Channel)
**Task:** Publish alerts to Redis pub/sub for real-time consumption

**Behavior:**
- Publish alerts to Redis topic `alerts.notifications`
- Other services can subscribe for real-time alerts
- Fallback to log channel if Redis unavailable
- No persistence (pub/sub only)

**API:**
```python
class RedisNotificationChannel:
    def __init__(
        self,
        bus: BusProto,
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Publish alert to Redis topic.

        Returns:
            True if successful, False if failed (uses fallback)
        """
        pass
```

**Files:**
- `alerts/channels/redis.py` (50 LOC)
- `tests/test_redis_channel.py`

**Acceptance:**
- Publishes to `alerts.notifications` topic
- Fallback to log channel if Redis unavailable
- Test verifies Redis publish
- Test verifies fallback behavior
- `make fmt lint type test` green

---

### Phase 11.5 — Webhook Notification Channel 📋
**Status:** Planned
**Dependencies:** 11.4 (Redis Notification Channel)
**Task:** HTTP webhook notification for external integrations

**Behavior:**
- POST alerts to configured webhook URL
- JSON payload format
- Retry logic (3 attempts with exponential backoff)
- Timeout: 5 seconds per attempt
- Fallback to log channel if all retries fail
- **Security: No secrets in config** (use env vars for URLs/tokens)

**Webhook Payload:**
```json
{
  "alert_id": "uuid",
  "timestamp": 1234567890000000000,
  "severity": "critical",
  "category": "killswitch",
  "source": "risk_engine",
  "title": "Kill Switch Triggered",
  "message": "Kill switch has been tripped",
  "labels": {"env": "live"},
  "annotations": {"runbook": "https://..."}
}
```

**API:**
```python
class WebhookNotificationChannel:
    def __init__(
        self,
        webhook_url: str,
        auth_token: str | None = None,  # From env var
        timeout_seconds: int = 5,
        max_retries: int = 3,
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """POST alert to webhook URL.

        Returns:
            True if successful, False if all retries failed
        """
        pass

    async def send_with_retry(
        self,
        payload: dict[str, Any]
    ) -> bool:
        """Send with exponential backoff retry."""
        pass
```

**Config Example:**
```yaml
# config/alerts.yaml
channels:
  webhook_primary:
    type: webhook
    url: "${NJORD_ALERT_WEBHOOK_URL}"  # From env var
    auth_token: "${NJORD_ALERT_WEBHOOK_TOKEN}"  # From env var
    enabled: true
    rate_limit_per_hour: 100
```

**Files:**
- `alerts/channels/webhook.py` (120 LOC)
- `tests/test_webhook_channel.py`

**Acceptance:**
- POSTs JSON payload to webhook URL
- Retry logic (3 attempts, exponential backoff)
- Timeout enforcement (5 seconds)
- Auth token from env var (not hardcoded)
- Fallback to log channel on failure
- Test includes retry and timeout scenarios
- `make fmt lint type test` green

---

### Phase 11.6 — Email Notification Channel (Stub) 📋
**Status:** Planned
**Dependencies:** 11.5 (Webhook Notification Channel)
**Task:** Email notification stub (no SMTP in Phase 11)

**Behavior:**
- Email channel stub for future implementation
- Logs email intent to alert log
- **No actual SMTP sending** (deferred to deployment)
- Config structure defined (SMTP host, port, credentials)
- Placeholder for future implementation

**API:**
```python
class EmailNotificationChannel:
    def __init__(
        self,
        smtp_config: dict[str, Any],
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Email notification (stub implementation).

        Current behavior:
            - Logs email intent to alert log
            - Returns True (no actual sending)

        Future implementation:
            - Connect to SMTP server
            - Send formatted email
            - Handle authentication
        """
        pass

    def format_email(self, alert: Alert) -> dict[str, str]:
        """Format alert as email (subject, body).

        Returns:
            {"subject": "...", "body": "...", "to": "..."}
        """
        pass
```

**Config Example:**
```yaml
# config/alerts.yaml
channels:
  email_ops:
    type: email
    smtp_host: "${NJORD_SMTP_HOST}"
    smtp_port: 587
    smtp_user: "${NJORD_SMTP_USER}"
    smtp_pass: "${NJORD_SMTP_PASS}"
    from_addr: "alerts@trading.internal"
    to_addrs: ["ops@trading.internal"]
    enabled: false  # Stub only in Phase 11
```

**Files:**
- `alerts/channels/email.py` (80 LOC stub)
- `tests/test_email_channel.py`

**Acceptance:**
- Logs email intent (no actual sending)
- Config structure defined (SMTP params)
- Email formatting works (subject, body)
- Returns success (stub always succeeds)
- Test verifies stub behavior (logs, no network I/O)
- `make fmt lint type test` green

---

### Phase 11.7 — Slack Notification Channel (Stub) 📋
**Status:** Planned
**Dependencies:** 11.6 (Email Notification Channel)
**Task:** Slack notification stub (no Slack API in Phase 11)

**Behavior:**
- Slack channel stub for future implementation
- Logs Slack intent to alert log
- **No actual Slack API calls** (deferred to deployment)
- Config structure defined (webhook URL, channel)
- Placeholder for future implementation

**API:**
```python
class SlackNotificationChannel:
    def __init__(
        self,
        webhook_url: str,  # Slack webhook URL
        channel: str,  # e.g., "#alerts"
        fallback: LogNotificationChannel | None = None
    ): ...

    async def send(self, alert: Alert) -> bool:
        """Slack notification (stub implementation).

        Current behavior:
            - Logs Slack intent to alert log
            - Returns True (no actual sending)

        Future implementation:
            - POST to Slack webhook URL
            - Format message with blocks/attachments
            - Handle rate limits
        """
        pass

    def format_slack_message(self, alert: Alert) -> dict[str, Any]:
        """Format alert as Slack message.

        Returns:
            Slack message payload (blocks format)
        """
        pass
```

**Slack Message Format:**
```json
{
  "channel": "#alerts",
  "username": "Njord Alerts",
  "icon_emoji": ":rotating_light:",
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "🚨 Kill Switch Triggered"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Severity:*\ncritical"},
        {"type": "mrkdwn", "text": "*Source:*\nrisk_engine"}
      ]
    }
  ]
}
```

**Config Example:**
```yaml
# config/alerts.yaml
channels:
  slack_ops:
    type: slack
    webhook_url: "${NJORD_SLACK_WEBHOOK_URL}"
    channel: "#alerts"
    enabled: false  # Stub only in Phase 11
```

**Files:**
- `alerts/channels/slack.py` (100 LOC stub)
- `tests/test_slack_channel.py`

**Acceptance:**
- Logs Slack intent (no actual sending)
- Config structure defined (webhook URL, channel)
- Slack message formatting works (blocks format)
- Returns success (stub always succeeds)
- Test verifies stub behavior (logs, no network I/O)
- `make fmt lint type test` green

---

### Phase 11.8 — Alert Service Daemon 📋
**Status:** Planned
**Dependencies:** 11.7 (Slack Notification Channel)
**Task:** Long-running alert service orchestrating all components

**Behavior:**
- Orchestrate AlertBus, RuleEngine, and all channels
- Subscribe to metrics and events
- Evaluate rules in real-time
- Route alerts to configured channels
- **Production gating: Check env var NJORD_ENABLE_ALERTS=1 before starting** (disabled by default)
- **Graceful degradation: If disabled, only expose health check** (no alert routing)
- Health check endpoint (HTTP `/health`)
- Graceful shutdown (SIGTERM handling)
- **Bind to localhost by default** (127.0.0.1)

**API:**
```python
class AlertService:
    def __init__(
        self,
        config: Config,
        bus: BusProto,
        bind_host: str = "127.0.0.1",
        health_port: int = 9092
    ): ...

    async def start(self) -> None:
        """Start alert service.

        Tasks:
            - Check NJORD_ENABLE_ALERTS=1 env var (exit early if disabled)
            - Load alert rules from config
            - Initialize notification channels
            - Start alert bus
            - Subscribe to telemetry.metrics
            - Expose health check endpoint

        Security:
            - Alert routing disabled by default (requires NJORD_ENABLE_ALERTS=1)
            - Prevents accidental alert noise during maintenance/testing
            - Health check always available (even when disabled)
        """
        pass

    async def run(self) -> None:
        """Main event loop."""
        pass

    async def health_check(self) -> dict[str, Any]:
        """Health check endpoint.

        Returns:
            {"status": "healthy", "rules_loaded": N, "channels_active": [...]}
        """
        pass

    async def shutdown(self) -> None:
        """Graceful shutdown (SIGTERM handler)."""
        pass
```

**Files:**
- `apps/alert_service/main.py` (200 LOC)
- `tests/test_alert_service.py`

**Acceptance:**
- Loads rules from `config/alerts.yaml`
- **Alert routing gated by NJORD_ENABLE_ALERTS=1 env var** (disabled by default)
- **Test verifies service exits early when NJORD_ENABLE_ALERTS unset** (no alert routing)
- **Test verifies health check works even when alerts disabled**
- Evaluates metrics in real-time (when enabled)
- Routes alerts to channels based on severity (when enabled)
- Health check accessible at `http://localhost:9092/health`
- **Security: Binds to localhost (127.0.0.1) by default**
- Graceful shutdown on SIGTERM
- Test includes end-to-end alert flow (metric → rule → channel) when enabled
- `make fmt lint type test` green

---

### Phase 11.9 — Alert CLI 📋
**Status:** Planned
**Dependencies:** 11.8 (Alert Service Daemon)
**Task:** CLI for alert management and testing

**Behavior:**
- List active alerts
- Fire test alert (for channel testing)
- Acknowledge/resolve alerts
- List configured rules
- Validate alert config
- Subscribe to live alerts (streaming)

**CLI Commands:**
```bash
# List active alerts
python -m alerts.cli list --severity critical

# Fire test alert
python -m alerts.cli test \
    --severity critical \
    --category system \
    --message "Test alert"

# Acknowledge alert
python -m alerts.cli ack <alert_id>

# Resolve alert
python -m alerts.cli resolve <alert_id>

# List alert rules
python -m alerts.cli rules --enabled-only

# Validate config
python -m alerts.cli validate --config config/alerts.yaml

# Stream live alerts (subscribe)
python -m alerts.cli stream --follow
```

**API:**
```python
class AlertCLI:
    def __init__(self, bus: BusProto, config_path: Path): ...

    async def list_alerts(
        self,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 50
    ) -> None:
        """List active alerts."""
        pass

    async def fire_test_alert(
        self,
        severity: str,
        category: str,
        message: str
    ) -> None:
        """Fire test alert for channel testing."""
        pass

    async def acknowledge_alert(self, alert_id: str) -> None:
        """Acknowledge alert."""
        pass

    async def resolve_alert(self, alert_id: str) -> None:
        """Resolve alert."""
        pass

    async def list_rules(self, enabled_only: bool = False) -> None:
        """List configured alert rules."""
        pass

    async def validate_config(self, config_path: Path) -> None:
        """Validate alert config (rules, channels)."""
        pass

    async def stream_alerts(self, follow: bool = False) -> None:
        """Subscribe to live alerts (streaming output)."""
        pass
```

**Files:**
- `alerts/cli.py` (250 LOC)
- `tests/test_alert_cli.py`

**Acceptance:**
- List alerts with filtering (severity, category)
- Test alert fires to all channels
- Acknowledge/resolve updates alert state
- Rules listing shows enabled/disabled status
- Config validation catches errors (invalid conditions, missing fields)
- Stream mode outputs alerts in real-time
- All CLI commands have --help text
- `make fmt lint type test` green

---

### Phase 11.10 — Alert Documentation 📋
**Status:** Planned
**Dependencies:** 11.9 (Alert CLI)
**Task:** Comprehensive documentation for alert system

**Deliverables:**

**1. Alert System Architecture (docs/alerts/ARCHITECTURE.md)**
- Component diagram (AlertBus, RuleEngine, Channels)
- Data flow: Metric → Rule → Alert → Channel → Notification
- Deduplication and rate limiting strategy
- Integration with Phase 9 (Metrics) and Phase 10 (Controller)

**2. Alert Rules Guide (docs/alerts/RULES.md)**
- Rule configuration format
- Condition syntax (>, <, >=, <=, ==, !=)
- Duration tracking mechanics
- Annotation templating
- Example rules for common scenarios

**3. Channel Configuration (docs/alerts/CHANNELS.md)**
- Channel types: log, redis, webhook, email (stub), slack (stub)
- Security best practices (env vars for secrets)
- Rate limiting configuration
- Fallback strategies

**4. Operations Runbook (docs/alerts/RUNBOOK.md)**
- Starting alert service
- Testing alert channels
- Troubleshooting alert delivery
- Common alert scenarios and responses

**5. API Reference (docs/alerts/API.md)**
- Alert contracts reference
- AlertBus API
- RuleEngine API
- NotificationChannel interface
- CLI command reference

**Files:**
- `docs/alerts/ARCHITECTURE.md`
- `docs/alerts/RULES.md`
- `docs/alerts/CHANNELS.md`
- `docs/alerts/RUNBOOK.md`
- `docs/alerts/API.md`

**Acceptance:**
- Architecture diagram shows all components
- Rules guide includes 5+ example rules
- Channels guide covers all supported types
- Runbook includes troubleshooting steps
- API reference documents all public interfaces
- All docs use consistent formatting (markdown)
- `make fmt lint type test` green (no code changes)

---

## Dependencies Summary

```
Phase 10 (Live Trade Controller) ✅
    └─> Phase 11.0 (Alert Contracts) — Alert, AlertRule, NotificationChannel
            └─> 11.1 (Alert Bus) — Routing, deduplication, rate limiting
                    └─> 11.2 (Rule Engine) — Metric evaluation, duration tracking
                            └─> 11.3 (Log Channel) — NDJSON alert logging
                                    └─> 11.4 (Redis Channel) — Pub/sub notifications
                                            └─> 11.5 (Webhook Channel) — HTTP POST with retry
                                                    └─> 11.6 (Email Channel) — Stub implementation
                                                            └─> 11.7 (Slack Channel) — Stub implementation
                                                                    └─> 11.8 (Alert Service) — Daemon orchestration
                                                                            └─> 11.9 (Alert CLI) — Management commands
                                                                                    └─> 11.10 (Documentation) — Guides and API reference
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---

## Phase 12 — Compliance & Audit 📋

**Purpose:** Implement comprehensive audit trail, deterministic replay validation, and regulatory compliance tooling.

**Current Status:** Phase 11 complete — Monitoring & Alerts fully operational
**Next Phase:** Phase 13 — Advanced Strategy Toolkit

---

### Phase 12.0 — Audit Contracts 📋
**Status:** Planned
**Dependencies:** 11.10 (Alert Documentation)
**Task:** Define audit-specific contracts and event types

**Contracts:**
```python
@dataclass(frozen=True)
class AuditEvent:
    """Immutable audit log entry."""
    event_id: str  # UUID
    timestamp_ns: int
    event_type: Literal["order", "fill", "risk_decision", "config_change", "killswitch", "session"]
    actor: str  # User, service name, or "system"
    action: str  # "create", "update", "delete", "approve", "deny", "trigger"
    resource_type: str  # "order", "position", "config", "killswitch"
    resource_id: str  # Order ID, position ID, config path, etc.
    before_state: dict[str, Any] | None  # State before action (JSON)
    after_state: dict[str, Any] | None  # State after action (JSON)
    metadata: dict[str, Any]  # Additional context
    checksum: str  # SHA256 of serialized event (tamper detection)

@dataclass(frozen=True)
class ReplaySession:
    """Replay validation session."""
    session_id: str  # UUID
    start_ts_ns: int
    end_ts_ns: int
    journals_replayed: list[str]  # Paths to journal files
    events_processed: int
    events_validated: int
    discrepancies: list[str]  # List of discrepancy descriptions
    status: Literal["running", "completed", "failed"]
    checksum: str  # SHA256 of all replayed events

@dataclass(frozen=True)
class OrderBookSnapshot:
    """Point-in-time order book state."""
    timestamp_ns: int
    symbol: str
    bids: list[tuple[float, float]]  # [(price, quantity), ...]
    asks: list[tuple[float, float]]  # [(price, quantity), ...]
    sequence_number: int  # Exchange sequence number
    checksum: str  # SHA256 of snapshot (integrity validation)
```

**Files:**
- `compliance/contracts.py` (120 LOC)
- `tests/test_audit_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- Checksum calculation deterministic (same input → same checksum)
- Validation: event_type/action enums valid, checksums non-empty
- `make fmt lint type test` green

---

### Phase 12.1 — Immutable Audit Logger 📋
**Status:** Planned
**Dependencies:** 12.0 (Audit Contracts)
**Task:** Append-only audit log writer with tamper detection

**Behavior:**
- Write audit events to append-only NDJSON files
- Separate audit log: `var/log/njord/audit.ndjson`
- Calculate SHA256 checksum for each event
- Maintain running checksum chain (each event includes prior checksum)
- **Immutability: File opened in append mode only** (no overwrite, no delete)
- Rotation handled externally (logrotate or similar)
- No buffering (immediate flush to disk)

**API:**
```python
class AuditLogger:
    def __init__(
        self,
        log_path: Path = Path("var/log/njord/audit.ndjson"),
        verify_chain: bool = True,
        loop: asyncio.AbstractEventLoop | None = None
    ): ...

    async def log_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> AuditEvent:
        """Log immutable audit event asynchronously.

        Behavior:
            - Uses background executor for file writes (non-blocking)
            - Flushes after each append (fsync)

        Returns:
            AuditEvent with calculated checksum
        """
        pass

    def calculate_checksum(self, event: AuditEvent) -> str:
        """Calculate SHA256 checksum of event.

        Includes:
            - All event fields except checksum itself
            - Prior event checksum (chain validation)
        """
        pass

    def verify_chain(self, events: list[AuditEvent]) -> bool:
        """Verify audit log chain integrity.

        Returns:
            True if chain intact, False if tampering detected
        """
        pass

    async def read_events(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None,
        event_type: str | None = None
    ) -> list[AuditEvent]:
        """Read audit events asynchronously with optional filtering."""
        pass
```

**Checksum Chain Example:**
```
Event 1: checksum = SHA256(event_1_data + "")
Event 2: checksum = SHA256(event_2_data + event_1_checksum)
Event 3: checksum = SHA256(event_3_data + event_2_checksum)
```

**Files:**
- `compliance/audit_logger.py` (180 LOC)
- `tests/test_audit_logger.py`

**Acceptance:**
- Writes events to `var/log/njord/audit.ndjson` (append-only)
- Checksum chain verification works (detects tampering)
- **Test verifies tamper detection** (modify event, verify fails)
- **Test verifies append-only** (cannot open in write mode)
- No buffering (fsync after each write)
- Read events with filtering (time range, event type)
- `make fmt lint type test` green

---

### Phase 12.2 — Service Instrumentation (Audit Hooks) 📋
**Status:** Planned
**Dependencies:** 12.1 (Immutable Audit Logger)
**Task:** Instrument core services with audit logging

**Behavior:**
- Add audit logging to critical operations across services
- Emit audit events for: orders, fills, risk decisions, config changes, kill-switch trips
- Include before/after state for all mutations
- **Performance: Async audit logging** (non-blocking)
- **Fallback: Log to stderr if audit logger unavailable** (no service failure)

**Instrumentation Points:**

**Risk Engine:**
```python
# Before/after for risk decisions
await audit_logger.log_event(
    event_type="risk_decision",
    actor="risk_engine",
    action="approve" if allowed else "deny",
    resource_type="order_intent",
    resource_id=intent.intent_id,
    before_state={"intent": intent.to_dict()},
    after_state={"decision": decision.to_dict()},
    metadata={"reason": decision.reason}
)
```

**Paper Trader / Broker:**
```python
# Order placement
await audit_logger.log_event(
    event_type="order",
    actor=f"broker_{venue}",
    action="create",
    resource_type="order",
    resource_id=order.client_order_id,
    before_state=None,
    after_state=order.to_dict(),
    metadata={"venue": venue, "symbol": order.symbol}
)
```

**Config Hot-Reload:**
```python
# Config changes
await audit_logger.log_event(
    event_type="config_change",
    actor="controller",
    action="reload",
    resource_type="config",
    resource_id=config_path.name,
    before_state={"hash": old_hash},
    after_state={"hash": new_hash},
    metadata={"path": str(config_path)}
)
```

**Kill Switch:**
```python
# Kill switch trips
await audit_logger.log_event(
    event_type="killswitch",
    actor="system",
    action="trigger",
    resource_type="killswitch",
    resource_id="global",
    before_state={"active": False},
    after_state={"active": True},
    metadata={"trigger_source": source}
)
```

**Files:**
- Update `apps/risk_engine/main.py` (+30 LOC)
- Update `apps/paper_trader/main.py` (+30 LOC)
- Update `apps/broker_binanceus/main.py` (+30 LOC)
- Update `controller/config_reloader.py` (+20 LOC)
- Update `core/kill_switch.py` (+20 LOC)
- `tests/test_audit_instrumentation.py`

**Acceptance:**
- Risk decisions logged with before/after state
- Orders logged (create, cancel, fill)
- Config changes logged with file hash
- Kill-switch events logged
- Async logging (non-blocking service operations)
- Fallback to stderr if audit logger fails
- Test verifies audit events emitted for each operation
- `make fmt lint type test` green

---

### Phase 12.3 — Deterministic Replay Engine 📋
**Status:** Planned
**Dependencies:** 12.2 (Service Instrumentation)
**Task:** Replay journal events and validate against audit log

**Behavior:**
- Read journals (OHLCV, trades, fills, orders, risk decisions)
- Replay events in chronological order
- Re-execute business logic (risk checks, fill simulation)
- Compare replayed state against audit log
- Detect discrepancies (missing events, state mismatches)
- Generate replay validation report

**API:**
```python
class ReplayEngine:
    def __init__(
        self,
        journal_dir: Path,
        audit_log_path: Path,
        config: Config
    ): ...

    async def replay_session(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        journals: list[str] | None = None  # Default: all journals
    ) -> ReplaySession:
        """Replay events and validate against audit log.

        Returns:
            ReplaySession with validation results
        """
        pass

    async def replay_event(self, event: dict[str, Any]) -> Any:
        """Replay single event (re-execute business logic)."""
        pass

    def validate_state(
        self,
        replayed_state: dict[str, Any],
        audit_state: dict[str, Any]
    ) -> list[str]:
        """Compare replayed vs. audit state.

        Returns:
            List of discrepancies (empty if match)
        """
        pass

    def generate_report(self, session: ReplaySession) -> str:
        """Generate human-readable validation report."""
        pass
```

**Replay Flow:**
1. Load journals (trades, orders, fills, risk decisions)
2. Sort events by timestamp_ns
3. For each event:
   - Replay event (re-execute logic)
   - Load corresponding audit event
   - Compare replayed state vs. audit state
   - Record discrepancies
4. Generate validation report

**Files:**
- `compliance/replay_engine.py` (300 LOC)
- `tests/test_replay_engine.py`

**Acceptance:**
- Replays events from journals in chronological order
- Re-executes risk checks (deterministic)
- Compares replayed fills vs. audit log fills
- Detects discrepancies (missing events, state mismatches)
- **Test verifies perfect replay** (no discrepancies for golden journals)
- **Test verifies discrepancy detection** (inject mismatch, report shows it)
- Generate report with discrepancy details
- `make fmt lint type test` green

---

### Phase 12.4 — Order Book Reconstruction 📋
**Status:** Planned
**Dependencies:** 12.3 (Deterministic Replay Engine)
**Task:** Reconstruct historical order book from market data journals

**Behavior:**
- Read market data journals (trades, order book snapshots)
- Rebuild order book state at any timestamp
- Validate reconstructed book against exchange snapshots
- Detect gaps (missing data, sequence number jumps)
- Calculate book statistics (spread, depth, imbalance)

**API:**
```python
class OrderBookReconstructor:
    def __init__(
        self,
        journal_dir: Path,
        symbol: str
    ): ...

    async def reconstruct_at_time(
        self,
        timestamp_ns: int
    ) -> OrderBookSnapshot:
        """Reconstruct order book state at specific time.

        Returns:
            OrderBookSnapshot with bids/asks/checksum
        """
        pass

    async def replay_book_updates(
        self,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> list[OrderBookSnapshot]:
        """Replay order book updates over time range.

        Returns:
            List of snapshots at each update
        """
        pass

    def validate_against_exchange(
        self,
        reconstructed: OrderBookSnapshot,
        exchange_snapshot: OrderBookSnapshot
    ) -> list[str]:
        """Validate reconstructed book vs. exchange snapshot.

        Returns:
            List of discrepancies (empty if match)
        """
        pass

    def calculate_book_stats(
        self,
        snapshot: OrderBookSnapshot
    ) -> dict[str, float]:
        """Calculate order book statistics.

        Returns:
            {"spread": ..., "bid_depth": ..., "ask_depth": ..., "imbalance": ...}
        """
        pass

    def detect_gaps(
        self,
        snapshots: list[OrderBookSnapshot]
    ) -> list[tuple[int, int]]:
        """Detect sequence number gaps.

        Returns:
            List of (expected_seq, actual_seq) tuples
        """
        pass
```

**Files:**
- `compliance/order_book.py` (250 LOC)
- `tests/test_order_book_reconstruction.py`

**Acceptance:**
- Reconstructs order book at any timestamp
- Validates against exchange snapshots
- **Test verifies reconstruction accuracy** (compare vs. golden snapshots)
- Detects sequence number gaps
- Calculates book statistics (spread, depth, imbalance)
- **Test verifies gap detection** (inject missing sequence, detect it)
- `make fmt lint type test` green

---

### Phase 12.5 — Audit Report Generator 📋
**Status:** Planned
**Dependencies:** 12.4 (Order Book Reconstruction)
**Task:** Generate comprehensive audit reports for compliance

**Behavior:**
- Generate daily/weekly/monthly audit summaries
- Include: order count, fill count, risk rejections, config changes, kill-switch events
- Calculate metrics: order-to-fill ratio, rejection rate, config change frequency
- Export to CSV, JSON, HTML formats
- Include checksum verification results

**Report Types:**

**1. Daily Trading Summary**
- Orders placed (count, total notional)
- Fills executed (count, total notional, avg slippage)
- Risk rejections (count, breakdown by reason)
- Kill-switch events (count, duration)
- Config changes (count, list of files)

**2. Audit Trail Verification**
- Total audit events
- Checksum chain status (intact/tampered)
- Replay validation results (discrepancies count)
- Missing events (expected vs. actual)

**3. Order Book Quality**
- Reconstruction success rate
- Sequence gaps detected
- Average spread by symbol
- Book depth percentiles

**API:**
```python
class AuditReportGenerator:
    def __init__(
        self,
        audit_log_path: Path,
        journal_dir: Path
    ): ...

    def generate_daily_summary(
        self,
        date: str  # YYYY-MM-DD
    ) -> dict[str, Any]:
        """Generate daily trading summary.

        Returns:
            Summary dict with all metrics
        """
        pass

    def generate_audit_verification(
        self,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> dict[str, Any]:
        """Generate audit trail verification report.

        Returns:
            Verification status with checksum results
        """
        pass

    def generate_order_book_quality(
        self,
        symbol: str,
        start_ts_ns: int,
        end_ts_ns: int
    ) -> dict[str, Any]:
        """Generate order book quality report.

        Returns:
            Quality metrics (gaps, spread, depth)
        """
        pass

    def export_to_csv(
        self,
        report: dict[str, Any],
        output_path: Path
    ) -> None:
        """Export report to CSV."""
        pass

    def export_to_html(
        self,
        report: dict[str, Any],
        output_path: Path
    ) -> None:
        """Export report to interactive HTML."""
        pass
```

**Files:**
- `compliance/report_generator.py` (280 LOC)
- `compliance/templates/audit_report.html` (embedded)
- `tests/test_report_generator.py`

**Acceptance:**
- Generates daily trading summaries
- Generates audit verification reports
- Generates order book quality reports
- Exports to CSV, JSON, HTML
- **Test verifies report accuracy** (compare vs. known event counts)
- HTML report includes interactive charts
- `make fmt lint type test` green

---

### Phase 12.6 — Compliance CLI 📋
**Status:** Planned
**Dependencies:** 12.5 (Audit Report Generator)
**Task:** CLI for audit operations and compliance tasks

**Behavior:**
- Verify audit log integrity (checksum chain)
- Replay events for validation
- Reconstruct order book at timestamp
- Generate audit reports
- Search audit log by criteria
- Export audit events

**CLI Commands:**
```bash
# Verify audit log integrity
python -m compliance.cli verify \
    --audit-log var/log/njord/audit.ndjson \
    --start-date 2025-01-01 \
    --end-date 2025-01-31

# Replay events
python -m compliance.cli replay \
    --start-ts 1234567890000000000 \
    --end-ts 1234567890999999999 \
    --journals var/log/njord/

# Reconstruct order book
python -m compliance.cli reconstruct-book \
    --symbol BTC/USDT \
    --timestamp 1234567890000000000

# Generate report
python -m compliance.cli report \
    --type daily \
    --date 2025-01-15 \
    --output audit_report.html

# Search audit log
python -m compliance.cli search \
    --event-type order \
    --actor risk_engine \
    --start-date 2025-01-01

# Export audit events
python -m compliance.cli export \
    --format csv \
    --start-date 2025-01-01 \
    --output audit_events.csv
```

**API:**
```python
class ComplianceCLI:
    def __init__(
        self,
        audit_log_path: Path,
        journal_dir: Path
    ): ...

    async def verify_integrity(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> None:
        """Verify audit log checksum chain."""
        pass

    async def replay_events(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        journals: list[str] | None = None
    ) -> None:
        """Replay events and display validation results."""
        pass

    async def reconstruct_book(
        self,
        symbol: str,
        timestamp_ns: int
    ) -> None:
        """Reconstruct and display order book."""
        pass

    async def generate_report(
        self,
        report_type: str,
        date: str | None = None,
        output_path: Path | None = None
    ) -> None:
        """Generate and save audit report."""
        pass

    async def search_audit_log(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> None:
        """Search audit log and display results."""
        pass

    async def export_events(
        self,
        format: str,  # csv, json, ndjson
        output_path: Path,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> None:
        """Export audit events to file."""
        pass
```

**Files:**
- `compliance/cli.py` (300 LOC)
- `tests/test_compliance_cli.py`

**Acceptance:**
- Verify command detects checksum tampering
- Replay command shows discrepancies
- Reconstruct command displays order book
- Report command generates HTML/CSV/JSON
- Search command filters by criteria
- Export command produces valid output files
- All commands have --help text
- `make fmt lint type test` green

---

### Phase 12.7 — Regulatory Export Templates 📋
**Status:** Planned
**Dependencies:** 12.6 (Compliance CLI)
**Task:** Pre-formatted export templates for regulatory reporting

**Behavior:**
- Define export schemas for common regulatory formats
- FIX protocol message export (orders, fills)
- Trade blotter export (CSV with required fields)
- Position reconciliation report
- Daily activity summary (regulatory format)

**Export Templates:**

**1. FIX Protocol Messages**
```python
# Export orders/fills in FIX 4.4 format
def export_fix_messages(
    events: list[AuditEvent],
    output_path: Path
) -> None:
    """Export as FIX 4.4 messages."""
    # Format: 8=FIX.4.4|9=...|35=D|...
    pass
```

**2. Trade Blotter (CSV)**
```csv
Date,Time,Symbol,Side,Quantity,Price,Commission,OrderID,FillID,Venue
2025-01-15,09:30:15.123,BTC/USDT,BUY,0.5,45000.00,22.50,ord_123,fill_456,binanceus
```

**3. Position Reconciliation**
```csv
Symbol,OpenQty,AvgPrice,CurrentPrice,UnrealizedPnL,RealizedPnL
BTC/USDT,0.5,45000.00,46000.00,500.00,0.00
```

**4. Daily Activity Summary**
```json
{
  "date": "2025-01-15",
  "firm_id": "NJORD",
  "orders_placed": 150,
  "orders_filled": 142,
  "orders_cancelled": 8,
  "total_buy_notional": 1500000.00,
  "total_sell_notional": 1480000.00,
  "net_position_change": 20000.00,
  "risk_rejections": 5
}
```

**API:**
```python
class RegulatoryExporter:
    def __init__(
        self,
        audit_log_path: Path,
        journal_dir: Path
    ): ...

    def export_fix_messages(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        output_path: Path
    ) -> None:
        """Export orders/fills as FIX 4.4 messages."""
        pass

    def export_trade_blotter(
        self,
        date: str,  # YYYY-MM-DD
        output_path: Path
    ) -> None:
        """Export daily trade blotter (CSV)."""
        pass

    def export_position_reconciliation(
        self,
        timestamp_ns: int,
        output_path: Path
    ) -> None:
        """Export position reconciliation report."""
        pass

    def export_daily_activity_summary(
        self,
        date: str,
        output_path: Path
    ) -> None:
        """Export daily activity summary (JSON)."""
        pass
```

**Files:**
- `compliance/regulatory_export.py` (220 LOC)
- `tests/test_regulatory_export.py`

**Acceptance:**
- FIX messages valid (parseable by FIX parser)
- Trade blotter includes all required fields
- Position reconciliation matches backtest results
- Daily activity summary accurate
- **Test verifies FIX format validity**
- **Test verifies CSV field completeness**
- `make fmt lint type test` green

---

### Phase 12.8 — Audit Service Daemon 📋
**Status:** Planned
**Dependencies:** 12.7 (Regulatory Export Templates)
**Task:** Long-running service for real-time audit logging

**Behavior:**
- Subscribe to all audit-relevant topics (orders, fills, risk decisions, config changes)
- Write events to immutable audit log in real-time
- Expose audit query API (HTTP `/audit/events`, `/audit/verify`)
- Health check endpoint (HTTP `/health`)
- **Bind to localhost by default** (127.0.0.1:9093)
- **Production gating: Require `NJORD_ENABLE_AUDIT=1` env var before routing events** (health check still served)
- Graceful shutdown (SIGTERM handling)

**API:**
```python
class AuditService:
    def __init__(
        self,
        config: Config,
        bus: BusProto,
        audit_logger: AuditLogger,
        bind_host: str = "127.0.0.1",
        port: int = 9093
    ): ...

    async def start(self) -> None:
        """Start audit service.

        Tasks:
            - Check `NJORD_ENABLE_AUDIT=1` (exit early if disabled)
            - Subscribe to audit-relevant topics
            - Start real-time audit logging
            - Expose HTTP API for queries
            - Expose health check endpoint
        """
        pass

    async def handle_event(self, topic: str, event: dict[str, Any]) -> None:
        """Handle incoming event and log to audit."""
        pass

    async def query_events(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None,
        event_type: str | None = None,
        actor: str | None = None
    ) -> list[AuditEvent]:
        """Query audit events via HTTP API."""
        pass

    async def verify_integrity(
        self,
        start_ts_ns: int | None = None,
        end_ts_ns: int | None = None
    ) -> dict[str, Any]:
        """Verify audit log integrity via HTTP API.

        Returns:
            {"status": "intact|tampered", "events_verified": N, "discrepancies": [...]}
        """
        pass
```

**HTTP Endpoints:**
```
GET  /audit/events?start_ts=...&end_ts=...&event_type=...&actor=...
GET  /audit/verify?start_ts=...&end_ts=...
GET  /health
```

**Files:**
- `apps/audit_service/main.py` (180 LOC)
- `tests/test_audit_service.py`

**Acceptance:**
- Subscribes to audit-relevant topics
- Logs events in real-time (async, non-blocking)
- Query API returns filtered events
- Verify API detects tampering
- Health check accessible at `http://localhost:9093/health`
- **Security: Binds to localhost (127.0.0.1) by default**
- **Audit routing gated by `NJORD_ENABLE_AUDIT=1` env var** (disabled by default)
- **Test verifies service exits early when audit disabled (health check only)**
- Graceful shutdown on SIGTERM
- Test includes end-to-end audit flow (event → log → query)
- `make fmt lint type test` green

---

### Phase 12.9 — Compliance Documentation 📋
**Status:** Planned
**Dependencies:** 12.8 (Audit Service Daemon)
**Task:** Comprehensive documentation for compliance and audit system

**Deliverables:**

**1. Audit System Architecture (docs/compliance/ARCHITECTURE.md)**
- Component diagram (AuditLogger, ReplayEngine, OrderBookReconstructor)
- Data flow: Event → Audit Log → Verification → Report
- Checksum chain mechanics
- Immutability guarantees

**2. Audit Trail Guide (docs/compliance/AUDIT_TRAIL.md)**
- Event types and schemas
- Checksum calculation details
- Tamper detection mechanics
- Best practices for log retention

**3. Replay Validation Guide (docs/compliance/REPLAY.md)**
- Replay engine usage
- Discrepancy interpretation
- Resolution procedures
- Example replay scenarios

**4. Regulatory Export Guide (docs/compliance/REGULATORY.md)**
- FIX message export
- Trade blotter format
- Position reconciliation
- Daily activity summary
- Compliance workflows

**5. Operations Runbook (docs/compliance/RUNBOOK.md)**
- Starting audit service
- Running integrity checks
- Generating audit reports
- Troubleshooting discrepancies
- Emergency procedures (log corruption, tampering detection)

**6. API Reference (docs/compliance/API.md)**
- AuditLogger API
- ReplayEngine API
- OrderBookReconstructor API
- RegulatoryExporter API
- CLI command reference
- HTTP API reference

**Files:**
- `docs/compliance/ARCHITECTURE.md`
- `docs/compliance/AUDIT_TRAIL.md`
- `docs/compliance/REPLAY.md`
- `docs/compliance/REGULATORY.md`
- `docs/compliance/RUNBOOK.md`
- `docs/compliance/API.md`

**Acceptance:**
- Architecture diagram shows all components
- Audit trail guide includes checksum examples
- Replay guide includes 3+ example scenarios
- Regulatory guide covers all export formats
- Runbook includes troubleshooting steps
- API reference documents all public interfaces
- All docs use consistent formatting (markdown)
- `make fmt lint type test` green (no code changes)

---

## Dependencies Summary

```
Phase 11 (Monitoring & Alerts) ✅
    └─> Phase 12.0 (Audit Contracts) — AuditEvent, ReplaySession, OrderBookSnapshot
            └─> 12.1 (Immutable Audit Logger) — Append-only logging, checksum chain
                    └─> 12.2 (Service Instrumentation) — Audit hooks in services
                            └─> 12.3 (Deterministic Replay Engine) — Validation against audit log
                                    └─> 12.4 (Order Book Reconstruction) — Historical book state
                                            └─> 12.5 (Audit Report Generator) — Compliance reports
                                                    └─> 12.6 (Compliance CLI) — Management commands
                                                            └─> 12.7 (Regulatory Export) — FIX, CSV, JSON formats
                                                                    └─> 12.8 (Audit Service) — Real-time daemon
                                                                            └─> 12.9 (Documentation) — Guides and API reference
```

Each task builds on the previous, maintaining clean separation of concerns and architectural integrity.

---

## Phases 13-16 (Outline Only)

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
