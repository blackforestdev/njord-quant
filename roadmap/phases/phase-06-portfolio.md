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
