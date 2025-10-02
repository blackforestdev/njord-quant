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
