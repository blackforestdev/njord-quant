## Phase 14 — Simulation Harness 📋

**Purpose:** Build comprehensive simulation infrastructure for stress testing, Monte Carlo analysis, and multi-day scenario validation.

**Current Status:** Phase 13 complete — Advanced Strategy Toolkit fully operational
**Next Phase:** Phase 15 — Deployment Framework

---

### Phase 14.0 — Simulation Foundations 📋
**Status:** Planned
**Dependencies:** 13.10 (Advanced Strategy Documentation)
**Task:** Establish simulation architecture and scenario contracts

**Critical Architectural Requirements:**
1. **Deterministic Replay:** All scenarios must be reproducible with fixed seeds
2. **Isolation:** Simulations run in isolated contexts (no cross-contamination)
3. **Performance:** Multi-scenario execution must complete in reasonable time (parallelization)
4. **Observability:** All simulation events logged with scenario metadata
5. **Clean Teardown:** Resources released properly after each scenario run

**Deliverables:**

#### 1. Simulation Scenario Contract
```python
@dataclass(frozen=True)
class SimulationScenario:
    """Configuration for a simulation run.

    WARNING: All scenarios must be deterministic and reproducible.
    - Use fixed RNG seeds
    - Use fixed clock for timestamp generation
    - No external network dependencies
    - No filesystem side effects outside designated simulation directories
    """
    scenario_id: str
    scenario_type: Literal["stress", "monte_carlo", "replay", "parameter_sweep"]
    description: str

    # Market data configuration
    symbols: list[str]
    start_ts_ns: int
    end_ts_ns: int
    data_source: Literal["historical", "synthetic", "hybrid"]

    # Strategy configuration
    strategies: list[dict[str, Any]]  # Strategy configs
    portfolio_config: dict[str, Any]

    # Scenario-specific parameters
    params: dict[str, Any]  # Stress: event triggers, Monte Carlo: trials count, etc.

    # Execution configuration
    execution_config: dict[str, Any]  # Execution algo settings
    slippage_config: dict[str, Any]

    # Determinism controls
    random_seed: int
    fixed_clock: bool = True

@dataclass(frozen=True)
class SimulationResult:
    """Result from a simulation run."""
    scenario_id: str
    scenario_type: str
    status: Literal["success", "failure", "timeout", "error"]

    # Performance metrics
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int

    # Risk metrics
    max_position_value: float
    max_leverage: float
    margin_calls: int
    kill_switch_trips: int

    # Execution metrics
    avg_slippage_bps: float
    fill_rate: float

    # Scenario-specific results
    scenario_metrics: dict[str, float]

    # Metadata
    duration_seconds: float
    error_message: str | None
    event_count: int
    log_path: str
```

#### 2. Simulation Engine Base
```python
class SimulationEngine(ABC):
    """Base class for simulation engines.

    Responsibilities:
    - Load scenario configuration
    - Initialize isolated simulation context
    - Execute scenario with deterministic controls
    - Collect results and cleanup resources
    """

    def __init__(
        self,
        data_reader: DataReader,
        output_dir: Path = Path("var/simulations")
    ):
        self.data_reader = data_reader
        self.output_dir = output_dir
        self.logger = structlog.get_logger()

    @abstractmethod
    def run_scenario(self, scenario: SimulationScenario) -> SimulationResult:
        """Execute scenario and return results.

        IMPORTANT: Must ensure isolation and determinism:
        - Create isolated context (separate portfolio, positions, etc.)
        - Use scenario.random_seed for all RNG operations
        - Use FixedClock if scenario.fixed_clock is True
        - Log all events to scenario-specific log file
        - Clean up resources in finally block

        Raises:
            SimulationError: If scenario execution fails
            TimeoutError: If scenario exceeds timeout
        """
        pass

    def _create_isolated_context(
        self,
        scenario: SimulationScenario
    ) -> SimulationContext:
        """Create isolated simulation context.

        Returns isolated:
        - Portfolio state
        - Position manager
        - Risk engine state
        - Strategy instances
        - Bus (in-memory, isolated)
        """
        pass

    def _cleanup_context(self, context: SimulationContext) -> None:
        """Clean up resources after scenario run."""
        pass
```

**Files:**
- `simulation/contracts.py` (SimulationScenario, SimulationResult, ~120 LOC)
- `simulation/engine.py` (SimulationEngine base, ~180 LOC)
- `simulation/context.py` (SimulationContext, isolated state, ~100 LOC)
- `scripts/benchmark_simulation.py` (Performance benchmarking utility, ~150 LOC)
- `tests/test_simulation_base.py`

**Acceptance:**
- SimulationScenario contract is frozen and fully typed
- SimulationResult includes all required metric categories
- All timestamps use `*_ns` suffix convention
- SimulationEngine.run_scenario enforces isolation (test verifies no state leakage between runs)
- Test verifies determinism: same scenario → same results (run twice, compare)
- Test verifies cleanup: resources released after scenario (no file descriptors leaked)
- **Test verifies RNG seeding: scenario.random_seed produces reproducible results**
- **Test verifies FixedClock integration: timestamps are deterministic**
- `make fmt lint type test` green

---

### Phase 14.1 — Multi-Day Replay Simulation 📋
**Status:** Planned
**Dependencies:** 14.0 (Simulation Foundations)
**Task:** Implement extended replay scenarios spanning multiple trading days

**Behavior:**
- Load historical data for multi-day period (e.g., 30 days)
- Replay market data events in chronological order
- Execute strategies and track portfolio evolution
- Handle overnight positions and session boundaries
- Detect regime changes and strategy adaptation
- Generate comprehensive report with daily breakdown

**API:**
```python
class MultiDayReplayEngine(SimulationEngine):
    def __init__(
        self,
        data_reader: DataReader,
        output_dir: Path = Path("var/simulations/replay")
    ):
        super().__init__(data_reader, output_dir)

    def run_scenario(self, scenario: SimulationScenario) -> SimulationResult:
        """Run multi-day replay scenario.

        Process:
        1. Load historical data for [start_ts_ns, end_ts_ns]
        2. Initialize portfolio and strategies
        3. For each trading day:
            - Replay market events
            - Execute strategy signals
            - Track intraday PnL
            - Mark positions to market at EOD
            - Log daily summary
        4. Generate final report with daily breakdown

        Returns:
            SimulationResult with scenario_metrics containing:
            - daily_pnl: list[float]
            - daily_sharpe: list[float]
            - daily_max_dd: list[float]
            - overnight_exposures: list[float]
        """
        pass

    def _split_into_trading_days(
        self,
        events: list[MarketEvent],
        session_boundary_hour: int = 0
    ) -> list[list[MarketEvent]]:
        """Split event stream into trading days.

        Args:
            events: Full event stream
            session_boundary_hour: Hour marking session boundary (UTC)

        Returns:
            List of daily event batches
        """
        pass

    def _mark_positions_to_market(
        self,
        portfolio: Portfolio,
        eod_prices: dict[str, float],
        eod_ts_ns: int
    ) -> None:
        """Mark positions to market at end of day."""
        pass
```

**Requirements:**
- Support 7-90 day replay periods
- Handle market data gaps gracefully (weekends, holidays)
- Track overnight position risk and funding costs
- Detect and log regime changes (volatility spikes, trend reversals)
- Generate daily PnL attribution (strategy, execution, overnight)

**Constraints:**
- No new runtime dependencies
- No network I/O in tests
- Should complete 30-day replay efficiently (benchmark separately, not enforced in CI)
- Memory usage bounded (stream processing, not batch loading, enforced in tests)
- Deterministic with fixed seed

**Files:**
- `simulation/replay.py` (MultiDayReplayEngine, ~250 LOC)
- `simulation/session.py` (Trading session utils, ~80 LOC)
- `tests/test_replay_simulation.py`

**Acceptance:**
- Handles 30-day replay scenarios correctly
- Daily PnL breakdown calculated accurately
- Overnight positions marked to market at EOD
- Handles market data gaps without errors
- Test includes 7-day replay with known outcome (golden test)
- Test verifies determinism: same seed → same daily PnL sequence
- Test verifies session boundary detection (splits days correctly)
- **Benchmark (optional, not in CI): 30-day replay completes in <60 seconds on reference hardware**
- **Benchmark (optional, not in CI): 90-day replay uses <500MB peak memory on reference hardware**
- `make fmt lint type test` green

**Note:** Performance benchmarks are goals, not hard test requirements. Actual performance varies by hardware. Use `scripts/benchmark_simulation.py` to measure on target deployment hardware.

---

### Phase 14.2 — Stress Test Scenarios 📋
**Status:** Planned
**Dependencies:** 14.1 (Multi-Day Replay)
**Task:** Implement predefined stress scenarios (flash crash, liquidity shock, etc.)

**Behavior:**
- Define library of stress scenarios (flash crash, liquidity crunch, correlation breakdown)
- Inject synthetic stress events into historical data
- Measure portfolio response (drawdown, recovery time, risk controls)
- Test kill-switch triggers and circuit breakers
- Generate stress test report with pass/fail criteria

**API:**
```python
@dataclass(frozen=True)
class StressEvent:
    """Synthetic stress event to inject into market data."""
    event_type: Literal["flash_crash", "liquidity_shock", "volatility_spike", "correlation_break"]
    trigger_ts_ns: int
    affected_symbols: list[str]
    params: dict[str, Any]  # Event-specific parameters

class StressTestEngine(SimulationEngine):
    def __init__(
        self,
        data_reader: DataReader,
        output_dir: Path = Path("var/simulations/stress")
    ):
        super().__init__(data_reader, output_dir)
        self.stress_scenarios = self._load_stress_library()

    def run_scenario(self, scenario: SimulationScenario) -> SimulationResult:
        """Run stress test scenario.

        Process:
        1. Load baseline historical data
        2. Inject stress events at trigger timestamps
        3. Replay modified event stream
        4. Monitor portfolio behavior during stress
        5. Measure recovery metrics
        6. Validate risk controls triggered correctly

        Returns:
            SimulationResult with scenario_metrics containing:
            - max_drawdown_during_stress: float
            - time_to_recovery_seconds: int
            - kill_switch_triggered: bool
            - positions_liquidated: int
            - risk_violations: int
        """
        pass

    def _inject_flash_crash(
        self,
        events: list[MarketEvent],
        crash_event: StressEvent
    ) -> list[MarketEvent]:
        """Inject flash crash: sudden 10-20% drop over 1-5 minutes.

        Simulates:
        - Rapid price decline
        - Widening spreads
        - Volume spike
        - Partial recovery after crash bottom
        """
        pass

    def _inject_liquidity_shock(
        self,
        events: list[MarketEvent],
        shock_event: StressEvent
    ) -> list[MarketEvent]:
        """Inject liquidity shock: orderbook thinning, wide spreads.

        Simulates:
        - 5-10x spread widening
        - 80% reduction in orderbook depth
        - Slippage increase
        - Slow recovery over 15-30 minutes
        """
        pass

    def _measure_stress_response(
        self,
        portfolio_snapshots: list[PortfolioSnapshot],
        stress_event: StressEvent
    ) -> dict[str, float]:
        """Measure portfolio response to stress event."""
        pass
```

**Stress Scenario Library:**
1. **Flash Crash:** 15% drop in 2 minutes, 50% recovery in 10 minutes
2. **Liquidity Shock:** Spreads widen 10x, depth drops 80%, lasts 20 minutes
3. **Volatility Spike:** Realized vol increases 5x, reverts over 1 hour
4. **Correlation Breakdown:** Cross-asset correlations flip sign suddenly
5. **Exchange Outage:** Market data stops for 5-30 minutes
6. **Funding Rate Shock:** Overnight funding rate spikes 10x

**Files:**
- `simulation/stress.py` (StressTestEngine, stress injection, ~300 LOC)
- `simulation/stress_library.yaml` (Predefined scenarios, ~100 lines)
- `tests/test_stress_scenarios.py`

**Acceptance:**
- All 6 stress scenarios implemented and tested
- Flash crash injection produces expected price trajectory
- Liquidity shock widens spreads correctly
- Test verifies kill-switch triggers during flash crash
- Test verifies risk engine blocks orders during liquidity shock
- Stress response metrics calculated accurately
- **Test verifies determinism: same stress scenario → same max drawdown**
- **Test verifies recovery measurement: time to return to pre-stress equity**
- Test includes pass/fail criteria (e.g., "max drawdown < 25% during flash crash")
- `make fmt lint type test` green

---

### Phase 14.3 — Monte Carlo Simulation 📋
**Status:** Planned
**Dependencies:** 14.2 (Stress Test Scenarios)
**Task:** Implement Monte Carlo simulation for parameter robustness and distribution analysis

**Behavior:**
- Generate N randomized scenarios (varying parameters, market conditions)
- Run backtest for each scenario in parallel
- Aggregate results into distribution of outcomes
- Calculate confidence intervals and tail risk
- Identify parameter sensitivity and failure modes

**API:**
```python
@dataclass(frozen=True)
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation."""
    num_trials: int
    parameter_ranges: dict[str, tuple[float, float]]  # param_name -> (min, max)
    distribution_type: Literal["uniform", "normal", "lognormal"]
    confidence_levels: list[float] = field(default_factory=lambda: [0.05, 0.25, 0.5, 0.75, 0.95])
    parallel_workers: int = 4

class MonteCarloEngine(SimulationEngine):
    def __init__(
        self,
        data_reader: DataReader,
        output_dir: Path = Path("var/simulations/monte_carlo")
    ):
        super().__init__(data_reader, output_dir)

    def run_scenario(self, scenario: SimulationScenario) -> SimulationResult:
        """Run Monte Carlo simulation.

        Process:
        1. Parse MonteCarloConfig from scenario.params
        2. Generate N parameter sets from ranges
        3. Run backtest for each parameter set (parallel)
        4. Aggregate results into distributions
        5. Calculate statistics and confidence intervals

        Returns:
            SimulationResult with scenario_metrics containing:
            - mean_pnl: float
            - median_pnl: float
            - pnl_std: float
            - pnl_percentiles: dict[float, float]  # confidence_level -> pnl
            - sharpe_distribution: list[float]
            - max_dd_distribution: list[float]
            - failure_rate: float  # % of trials with negative PnL
        """
        pass

    def _generate_parameter_sets(
        self,
        config: MonteCarloConfig,
        base_seed: int
    ) -> list[dict[str, float]]:
        """Generate N randomized parameter sets.

        IMPORTANT: Must use base_seed for reproducibility.
        Each trial gets seed = base_seed + trial_index.
        """
        pass

    def _run_trial(
        self,
        trial_idx: int,
        params: dict[str, float],
        scenario: SimulationScenario
    ) -> SimulationResult:
        """Run single Monte Carlo trial with given parameters."""
        pass

    def _aggregate_results(
        self,
        results: list[SimulationResult],
        config: MonteCarloConfig
    ) -> dict[str, Any]:
        """Aggregate trial results into distributions and statistics."""
        pass
```

**Requirements:**
- Support 100-10,000 trial runs
- Parallel execution across multiple workers
- Deterministic with base seed (reproducible distributions)
- Memory-efficient (stream results, don't accumulate all in memory)
- Generate distribution plots (histograms, CDFs)

**Constraints:**
- No new runtime dependencies
- Should complete 1000 trials efficiently (benchmark separately, not enforced in CI)
- Memory usage bounded (process results incrementally, enforced in tests)
- Deterministic: same seed → same distribution

**Files:**
- `simulation/monte_carlo.py` (MonteCarloEngine, ~280 LOC)
- `simulation/distributions.py` (Statistical aggregation, ~120 LOC)
- `scripts/benchmark_monte_carlo.py` (Monte Carlo performance benchmarks, ~100 LOC)
- `tests/test_monte_carlo.py`

**Acceptance:**
- Generates N parameter sets from ranges correctly
- Runs trials in parallel (test verifies speedup vs sequential with small N=10)
- Aggregates results into distributions accurately
- Calculates confidence intervals correctly (test vs known distribution)
- Test verifies determinism: same base_seed → same distribution
- **Test verifies reproducibility: run twice with same seed → identical percentiles**
- **Benchmark (optional, not in CI): 1000 trials complete in <5 minutes with 4 workers on reference hardware**
- **Benchmark (optional, not in CI): 10,000 trials use <1GB peak memory on reference hardware**
- Test includes parameter sensitivity analysis (identify most impactful param)
- `make fmt lint type test` green

**Note:** Performance benchmarks are goals, not hard test requirements. CI tests use small N (10-100 trials) for speed. Use `scripts/benchmark_monte_carlo.py` with full trial counts on target deployment hardware.

---

### Phase 14.4 — Scenario Batch Runner 📋
**Status:** Planned
**Dependencies:** 14.3 (Monte Carlo Simulation)
**Task:** Build CLI and orchestration for running multiple scenarios in batch

**Behavior:**
- Load scenario suite from YAML configuration
- Execute scenarios sequentially or in parallel
- Track progress and handle failures gracefully
- Generate comparative report across scenarios
- Store results in structured format for analysis

**API:**
```python
class ScenarioBatchRunner:
    """Orchestrate execution of multiple simulation scenarios."""

    def __init__(
        self,
        engines: dict[str, SimulationEngine],  # scenario_type -> engine
        output_dir: Path = Path("var/simulations/batch")
    ):
        self.engines = engines
        self.output_dir = output_dir
        self.logger = structlog.get_logger()

    def run_batch(
        self,
        scenarios: list[SimulationScenario],
        parallel: bool = False,
        max_workers: int = 4,
        fail_fast: bool = False
    ) -> BatchResult:
        """Execute batch of scenarios.

        Args:
            scenarios: List of scenarios to execute
            parallel: Run scenarios in parallel (default: sequential)
            max_workers: Number of parallel workers (if parallel=True)
            fail_fast: Stop on first failure (default: continue)

        Returns:
            BatchResult with summary statistics and individual results
        """
        pass

    def _run_single_scenario(
        self,
        scenario: SimulationScenario
    ) -> SimulationResult:
        """Run single scenario with appropriate engine."""
        pass

    def _generate_comparative_report(
        self,
        results: list[SimulationResult],
        output_path: Path
    ) -> None:
        """Generate HTML report comparing scenario results.

        Report includes:
        - Summary table (PnL, Sharpe, Max DD per scenario)
        - Distribution comparisons (Monte Carlo scenarios)
        - Stress test pass/fail matrix
        - Correlation analysis across scenarios
        """
        pass

@dataclass(frozen=True)
class BatchResult:
    """Result from batch scenario execution."""
    total_scenarios: int
    successful: int
    failed: int
    skipped: int
    total_duration_seconds: float
    results: list[SimulationResult]
    summary_stats: dict[str, float]
    report_path: str
```

**CLI:**
```bash
# Run single scenario
python -m simulation.cli run --scenario config/scenarios/flash_crash.yaml

# Run scenario suite
python -m simulation.cli batch --suite config/scenarios/stress_suite.yaml --parallel --workers 4

# List available scenarios
python -m simulation.cli list

# Generate report from stored results
python -m simulation.cli report --results var/simulations/batch/2025-10-02_run1/
```

**Files:**
- `simulation/batch.py` (ScenarioBatchRunner, BatchResult, ~200 LOC)
- `simulation/cli.py` (CLI interface, ~150 LOC)
- `simulation/reporting.py` (Comparative report generation, ~180 LOC)
- `config/scenarios/stress_suite.yaml` (Example scenario suite)
- `tests/test_batch_runner.py`

**Acceptance:**
- Batch runner executes scenarios sequentially correctly
- Parallel execution completes faster than sequential (test verifies speedup)
- Handles individual scenario failures gracefully (continues or stops per fail_fast)
- Generates comparative HTML report with all required sections
- CLI commands work correctly (run, batch, list, report)
- Test verifies determinism: same scenario suite → same batch results
- **Test verifies parallelization correctness: parallel results match sequential**
- **Test verifies fail_fast: stops immediately on first failure when enabled**
- **Test verifies progress tracking: logs scenario completion percentage**
- `make fmt lint type test` green

---

### Phase 14.5 — Synthetic Market Data Generator 📋
**Status:** Planned
**Dependencies:** 14.4 (Scenario Batch Runner)
**Task:** Generate realistic synthetic market data for testing edge cases

**Behavior:**
- Generate OHLCV bars with configurable statistical properties
- Simulate orderbook dynamics (bid/ask spreads, depth)
- Inject specific patterns (trends, mean reversion, volatility clusters)
- Ensure statistical realism (fat tails, autocorrelation, etc.)
- Support deterministic generation (seeded RNG)

**API:**
```python
@dataclass(frozen=True)
class SyntheticMarketConfig:
    """Configuration for synthetic market data generation."""
    symbol: str
    start_ts_ns: int
    end_ts_ns: int
    bar_duration_seconds: int

    # Statistical properties
    initial_price: float
    drift: float  # Expected return per bar
    volatility: float  # Annualized volatility
    mean_reversion: float  # Mean reversion strength (0-1)

    # Microstructure
    avg_spread_bps: float
    spread_volatility: float
    avg_volume: float
    volume_autocorr: float

    # Pattern injection
    inject_trends: bool = False
    trend_params: dict[str, Any] | None = None
    inject_volatility_clusters: bool = False

    # Determinism
    random_seed: int

class SyntheticMarketGenerator:
    """Generate realistic synthetic market data."""

    def __init__(self, random_seed: int = 42):
        self.rng = np.random.default_rng(random_seed)

    def generate_ohlcv(
        self,
        config: SyntheticMarketConfig
    ) -> pd.DataFrame:
        """Generate synthetic OHLCV bars.

        Process:
        1. Generate price path using geometric Brownian motion with mean reversion
        2. Add microstructure noise (bid/ask bounce)
        3. Inject patterns if configured (trends, volatility clusters)
        4. Generate OHLC from price ticks
        5. Generate volume with autocorrelation

        Returns:
            DataFrame with columns: timestamp_ns, open, high, low, close, volume
        """
        pass

    def _generate_price_path(
        self,
        config: SyntheticMarketConfig
    ) -> np.ndarray:
        """Generate underlying price path using GBM + mean reversion.

        Model: dP = drift * P * dt + volatility * P * dW - mean_reversion * (P - P0) * dt
        Where:
        - P0 is initial price
        - dW is Wiener process increment
        - mean_reversion pulls price back to P0
        """
        pass

    def _inject_trend(
        self,
        prices: np.ndarray,
        trend_start_idx: int,
        trend_duration: int,
        trend_strength: float
    ) -> np.ndarray:
        """Inject trend into price path."""
        pass

    def _generate_volume(
        self,
        num_bars: int,
        avg_volume: float,
        autocorr: float
    ) -> np.ndarray:
        """Generate volume series with autocorrelation.

        Uses AR(1) process: V[t] = (1-autocorr)*avg + autocorr*V[t-1] + noise
        """
        pass
```

**Requirements:**
- Generate 1-90 days of synthetic data
- Realistic statistical properties (test vs historical data distributions)
- Support multiple patterns (trending, ranging, volatile, quiet)
- Deterministic with seed (reproducible)
- Fast generation (benchmark separately, not enforced in CI)

**Constraints:**
- No new runtime dependencies (use numpy only)
- Deterministic with fixed seed
- Memory efficient (stream generation for very long series)

**Files:**
- `simulation/synthetic.py` (SyntheticMarketGenerator, ~250 LOC)
- `simulation/patterns.py` (Pattern injection utilities, ~100 LOC)
- `scripts/benchmark_synthetic_data.py` (Synthetic data generation benchmarks, ~80 LOC)
- `tests/test_synthetic_data.py`

**Acceptance:**
- Generates OHLCV bars with correct timestamps and bar duration
- Price path follows GBM + mean reversion model correctly
- Volume has correct autocorrelation (test vs theoretical ACF)
- Trend injection creates detectable uptrend/downtrend
- Test verifies determinism: same seed → identical price paths
- **Test verifies statistical realism: compare distributions vs historical data (use small sample for CI)**
- **Benchmark (optional, not in CI): generate 30 days of 1-min bars in <1 second on reference hardware**
- **Test verifies mean reversion: prices oscillate around initial price over time**
- Test includes volatility clustering (GARCH-like behavior)
- `make fmt lint type test` green

**Note:** Performance benchmarks are goals. CI tests use smaller samples (1-3 days, 5-min bars) for speed. Use `scripts/benchmark_synthetic_data.py` for full-scale generation benchmarks.

---

### Phase 14.6 — Scenario Analysis Tools 📋
**Status:** Planned
**Dependencies:** 14.5 (Synthetic Market Data)
**Task:** Build analysis toolkit for comparing scenario results and identifying failure modes

**Behavior:**
- Load batch simulation results from disk
- Compare metrics across scenarios (PnL, Sharpe, drawdown distributions)
- Identify outliers and failure modes
- Perform sensitivity analysis (which parameters matter most)
- Generate diagnostic visualizations

**API:**
```python
class ScenarioAnalyzer:
    """Analyze and compare simulation scenario results."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.results: list[SimulationResult] = []
        self._load_results()

    def compare_scenarios(
        self,
        metric: str = "total_pnl",
        group_by: str | None = None
    ) -> pd.DataFrame:
        """Compare scenarios by metric.

        Args:
            metric: Metric to compare (total_pnl, sharpe_ratio, max_drawdown, etc.)
            group_by: Optional grouping (scenario_type, strategy_name, etc.)

        Returns:
            DataFrame with scenarios as rows, statistics as columns
        """
        pass

    def identify_failure_modes(
        self,
        threshold_pnl: float = 0.0,
        threshold_drawdown: float = 0.3
    ) -> list[SimulationResult]:
        """Identify scenarios that failed risk criteria.

        Returns:
            List of failed scenarios with failure reasons
        """
        pass

    def parameter_sensitivity(
        self,
        parameter_name: str,
        metric: str = "total_pnl"
    ) -> dict[str, float]:
        """Analyze sensitivity of metric to parameter.

        Computes correlation and regression slope between parameter and metric.

        Returns:
            {
                "correlation": float,
                "slope": float,
                "r_squared": float
            }
        """
        pass

    def plot_distribution_comparison(
        self,
        scenario_ids: list[str],
        metric: str = "total_pnl",
        output_path: Path | None = None
    ) -> None:
        """Plot distribution comparison across scenarios.

        For Monte Carlo scenarios, plots overlaid histograms and CDFs.
        For stress scenarios, plots bar chart with error bars.
        """
        pass

class FailureModeDetector:
    """Detect and categorize failure modes in simulation results."""

    def detect_failures(
        self,
        results: list[SimulationResult]
    ) -> dict[str, list[SimulationResult]]:
        """Categorize failures by type.

        Categories:
        - high_drawdown: Max DD > 30%
        - negative_pnl: Total PnL < 0
        - low_sharpe: Sharpe ratio < 0.5
        - kill_switch: Kill switch triggered
        - timeout: Scenario timed out
        - error: Exception during execution

        Returns:
            Dictionary mapping category to failed scenarios
        """
        pass
```

**Requirements:**
- Load and parse stored simulation results (NDJSON format)
- Generate comparative statistics (mean, median, std, percentiles)
- Identify parameter sensitivity (which params impact PnL most)
- Detect failure patterns (common causes of negative outcomes)
- Visualize distributions (optional: requires matplotlib)

**Constraints:**
- No new runtime dependencies for core analysis
- matplotlib optional (skip plots if not installed)
- Handle large result sets efficiently (1000+ scenarios)

**Files:**
- `simulation/analysis.py` (ScenarioAnalyzer, FailureModeDetector, ~280 LOC)
- `simulation/visualizations.py` (Plotting utilities, optional, ~150 LOC)
- `tests/test_scenario_analysis.py`

**Acceptance:**
- Loads simulation results from NDJSON correctly
- Compares scenarios by metric accurately
- Identifies failure modes correctly (test with known failures)
- Parameter sensitivity analysis produces correct correlations
- Test verifies failure categorization (high_drawdown, negative_pnl, etc.)
- **Test verifies sensitivity analysis: parameter with known impact detected**
- **Test includes statistical validation: distributions match expected properties**
- Optional: Test verifies plots generated (if matplotlib available)
- `make fmt lint type test` green

---

### Phase 14.7 — Simulation Documentation 📋
**Status:** Planned
**Dependencies:** 14.6 (Scenario Analysis Tools)
**Task:** Document simulation harness architecture, scenario library, and usage patterns

**Deliverables:**

#### 1. Architecture Documentation
**File:** `docs/simulation/ARCHITECTURE.md`
- Simulation engine design and isolation guarantees
- Scenario type hierarchy (stress, Monte Carlo, replay)
- Determinism enforcement mechanisms
- Resource management and cleanup

#### 2. Scenario Library Guide
**File:** `docs/simulation/SCENARIOS.md`
- Predefined stress scenarios (flash crash, liquidity shock, etc.)
- Monte Carlo parameter ranges and distributions
- Replay scenario configuration examples
- Custom scenario creation guide

#### 3. Usage Guide
**File:** `docs/simulation/USAGE.md`
- CLI quickstart examples
- Batch execution workflows
- Result analysis patterns
- Performance benchmarking guide (using scripts/benchmark_*.py)
- Troubleshooting common issues

#### 4. API Reference
**File:** `docs/simulation/API.md`
- SimulationEngine interface documentation
- Scenario configuration schema
- Result format specification
- Extension points for custom engines

**Files:**
- `docs/simulation/ARCHITECTURE.md` (~400 lines)
- `docs/simulation/SCENARIOS.md` (~300 lines)
- `docs/simulation/USAGE.md` (~250 lines)
- `docs/simulation/API.md` (~200 lines)

**Acceptance:**
- ARCHITECTURE.md covers all simulation engine types
- SCENARIOS.md documents all predefined scenarios with examples
- USAGE.md includes CLI examples for common tasks and performance benchmarking guide
- API.md provides clear interface documentation
- Performance benchmarking section explains hardware-dependent nature of benchmarks
- All code snippets in docs are valid (test via doctest or manual verification)
- Cross-references between docs are accurate
- `make fmt lint type test` green (no code changes)

---

**Phase 14 Acceptance Criteria:**
- [ ] All 7 tasks completed (14.0-14.7)
- [ ] `make fmt lint type test` green
- [ ] Simulation engines enforce isolation (no state leakage between scenarios)
- [ ] All scenarios deterministic with fixed seeds
- [ ] Multi-day replay handles 30-day periods correctly
- [ ] All 6 stress scenarios implemented and tested
- [ ] Monte Carlo runs 1000 trials in <5 minutes (4 workers)
- [ ] Batch runner supports parallel execution
- [ ] Synthetic data generator produces realistic market data
- [ ] Scenario analyzer identifies failure modes correctly
- [ ] Documentation covers architecture, scenarios, usage, and API
- [ ] Performance benchmarks documented (see scripts/benchmark_simulation.py):
  - 30-day replay: target <60 seconds on reference hardware
  - 1000 Monte Carlo trials: target <5 minutes with 4 workers
  - Synthetic data generation: target <1 second for 30 days
- [ ] Memory usage validated (enforced in tests):
  - Bounded caches and streaming processing (no unbounded growth)
  - Benchmarks (optional): 90-day replay <500MB, 10k trials <1GB on reference hardware

---

## Integration with Existing System

### Simulation Flow
```
Scenario Configuration (YAML)
    ↓
ScenarioBatchRunner
    ↓
SimulationEngine (Stress/MonteCarlo/Replay)
    ↓
Isolated SimulationContext
    ↓
BacktestEngine (reused from Phase 5)
    ↓
Strategy Execution (reused from Phase 3)
    ↓
SimulationResult
    ↓
ScenarioAnalyzer
    ↓
Reports & Visualizations
```

### Example Simulation Session
```bash
# 1. Run stress test suite
python -m simulation.cli batch \
    --suite config/scenarios/stress_suite.yaml \
    --parallel --workers 4 \
    --output var/simulations/stress_2025_10_02

# 2. Run Monte Carlo parameter sweep
python -m simulation.cli run \
    --scenario config/scenarios/monte_carlo_trendline.yaml \
    --output var/simulations/mc_trendline

# 3. Analyze results
python -m simulation.cli report \
    --results var/simulations/stress_2025_10_02 \
    --output reports/stress_analysis.html

# 4. Compare scenarios
python -m simulation.analysis compare \
    --results var/simulations/stress_2025_10_02 \
    --metric sharpe_ratio \
    --output reports/scenario_comparison.csv
```

---

## Dependencies Summary

```
Phase 13 (Advanced Strategy Toolkit) ✅
    └─> Phase 14.0 (Simulation Foundations) — Scenario contracts, engine base
            └─> 14.1 (Multi-Day Replay) — Extended backtests
                    └─> 14.2 (Stress Tests) — Flash crash, liquidity shock
                            └─> 14.3 (Monte Carlo) — Parameter robustness
                                    └─> 14.4 (Batch Runner) — Orchestration + CLI
                                            └─> 14.5 (Synthetic Data) — Edge case generation
                                                    └─> 14.6 (Analysis Tools) — Result comparison
                                                            └─> 14.7 (Documentation) — User guides
```

Each task builds on the previous, with clear separation between scenario types (replay, stress, Monte Carlo) and shared infrastructure (engine base, batch runner, analysis).

---
