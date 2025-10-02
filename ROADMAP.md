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

## Phases 8-16 (Outline Only)

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
