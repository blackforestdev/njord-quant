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
