## Phase 8 — Execution Layer 📋

**Purpose:** Implement sophisticated order execution algorithms, smart routing, and realistic slippage/fee simulation.

**Current Status:** Phase 7 complete — Research API fully operational
**Next Phase:** Phase 9 — Metrics & Telemetry

---

### Phase 8.0 — Execution Layer Foundations ✅
**Status:** Complete
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

### Phase 8.1 — Execution Contracts ✅
**Status:** Complete
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

### Phase 8.2 — TWAP Algorithm ✅
**Status:** Complete
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
