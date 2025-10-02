# Research API Guide

The Research API provides tools for offline data analysis, backtesting evaluation, and strategy research.

## Overview

The Research API consists of 8 main modules:

1. **DataReader** — Load journal data into pandas DataFrames
2. **DataAggregator** — Resample OHLCV and calculate technical indicators
3. **PerformanceAnalyzer** — Calculate performance metrics from backtest results
4. **StrategyComparison** — Compare multiple strategies side-by-side
5. **NotebookHelper** — Jupyter-friendly plotting and display utilities
6. **DataExporter** — Export data to CSV, Parquet, and JSON formats
7. **DataValidator** — Validate data quality and detect anomalies
8. **CLI** — Command-line interface for common operations

## Installation

The research API requires optional dependencies:

```bash
pip install -e ".[research]"
```

This installs: pandas, pandas-stubs, pyarrow, matplotlib, jupyter, notebook.

## Quick Start

### Loading Data

```python
from research.data_reader import DataReader

# Initialize reader
reader = DataReader("var/journals")

# Load OHLCV data
df = reader.read_ohlcv(
    symbol="ATOM/USDT",
    timeframe="1m",
    start_ts=1704067200000000000,
    end_ts=1704412800000000000
)

print(df.head())
```

### Calculating Indicators

```python
from research.aggregator import DataAggregator

aggregator = DataAggregator()

# Add technical indicators
df_with_indicators = aggregator.add_indicators(
    df,
    indicators=["sma_20", "ema_50", "rsi_14", "macd", "bbands_20"]
)

print(df_with_indicators.columns)
```

### Analyzing Performance

```python
from research.performance import PerformanceAnalyzer

# Load fills and positions
fills_df = reader.read_fills(
    strategy_id="my_strategy",
    start_ts=start_ts,
    end_ts=end_ts
)

positions_df = reader.read_positions(
    portfolio_id="main",
    start_ts=start_ts,
    end_ts=end_ts
)

# Analyze performance
analyzer = PerformanceAnalyzer(fills_df, positions_df)

# Calculate PnL time series
pnl_ts = analyzer.calculate_pnl_timeseries(resample_freq="1D")

# Analyze drawdowns
drawdowns = analyzer.analyze_drawdowns()
print(f"Largest drawdown: {drawdowns['depth_pct'].max():.2f}%")

# Trade distribution
trade_stats = analyzer.analyze_trade_distribution()
print(f"Win rate: {trade_stats['win_rate']:.1f}%")
```

### Comparing Strategies

```python
from research.comparison import StrategyComparison
from backtest.contracts import BacktestResult

# Load backtest results (assume we have result_a and result_b)
results = {
    "strategy_a": result_a,
    "strategy_b": result_b
}

# Compare strategies
comparison = StrategyComparison(results)

# Normalize equity curves
normalized_curves = comparison.normalize_equity_curves(target_capital=100000.0)

# Compare metrics
metrics_df = comparison.compare_metrics()
print(metrics_df)

# Statistical significance
sig_test = comparison.statistical_significance(
    "strategy_a",
    "strategy_b",
    method="ttest"
)
print(f"P-value: {sig_test['p_value']:.4f}")
```

### Jupyter Notebooks

```python
from research.notebook_helpers import NotebookHelper

helper = NotebookHelper()

# Quick equity plot
fig = helper.quick_plot_equity(result, title="Strategy Performance")

# Compare multiple strategies
fig = helper.compare_equity_curves(
    results,
    normalize=True,
    title="Strategy Comparison"
)

# Summary table
summary = helper.quick_summary_table(results)
display(summary)

# Metrics heatmap
fig = helper.display_metrics_heatmap(results)
```

### Exporting Data

```python
from research.export import DataExporter

exporter = DataExporter(reader)

# Export to CSV
exporter.export_ohlcv_to_csv(
    symbol="ATOM/USDT",
    timeframe="1m",
    start_ts=start_ts,
    end_ts=end_ts,
    output_path="data/atom_1m.csv"
)

# Export to Parquet with compression
exporter.export_ohlcv_to_parquet(
    symbol="ATOM/USDT",
    timeframe="1m",
    start_ts=start_ts,
    end_ts=end_ts,
    output_path="data/atom_1m.parquet",
    compression="snappy"
)

# Export backtest results to JSON
exporter.export_backtest_results_to_json(
    results,
    output_path="results/comparison.json"
)
```

### Validating Data Quality

```python
from research.validator import DataValidator

validator = DataValidator(reader)

# Generate quality report
report = validator.generate_quality_report(
    symbol="ATOM/USDT",
    timeframe="1m",
    start_ts=start_ts,
    end_ts=end_ts
)

print(f"Quality score: {report['summary']['quality_score']:.1f}/100")
print(f"Gaps: {report['summary']['total_gaps']}")
print(f"Spikes: {report['summary']['total_spikes']}")
print(f"Consistency issues: {report['summary']['total_consistency_issues']}")

# Check specific issues
gaps = validator.check_gaps("ATOM/USDT", "1m", start_ts, end_ts)
for gap_start, gap_end in gaps:
    print(f"Gap: {gap_start} to {gap_end}")
```

## Command-Line Interface

### Export Data

```bash
# Export OHLCV to CSV
python -m research.cli export-ohlcv \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2024-01-01 \
    --end 2024-01-31 \
    --format csv \
    --output data/atom_jan.csv

# Export to Parquet with gzip compression
python -m research.cli export-ohlcv \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2024-01-01 \
    --end 2024-01-31 \
    --format parquet \
    --compression gzip \
    --output data/atom_jan.parquet
```

### Validate Data Quality

```bash
# Console output
python -m research.cli validate \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2024-01-01 \
    --end 2024-01-31

# Save detailed report
python -m research.cli validate \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2024-01-01 \
    --end 2024-01-31 \
    --output quality_report.json
```

### List Available Data

```bash
python -m research.cli list-data
```

### Compare Backtest Results

```bash
python -m research.cli compare-backtests \
    --results var/backtest/strategy_a.json \
    --results var/backtest/strategy_b.json \
    --output comparison.csv
```

## Common Workflows

### Workflow 1: Data Quality Check

```python
# 1. Load data
reader = DataReader("var/journals")
validator = DataValidator(reader)

# 2. Run validation
report = validator.generate_quality_report(
    symbol="ATOM/USDT",
    timeframe="1m",
    start_ts=start_ts,
    end_ts=end_ts
)

# 3. Review issues
if report['summary']['quality_score'] < 90:
    print("⚠️  Data quality issues detected:")

    if report['summary']['total_gaps'] > 0:
        print(f"  - {report['summary']['total_gaps']} gaps in time series")

    if report['summary']['total_spikes'] > 0:
        print(f"  - {report['summary']['total_spikes']} price spikes")

    if report['summary']['total_consistency_issues'] > 0:
        print(f"  - {report['summary']['total_consistency_issues']} OHLCV inconsistencies")
```

### Workflow 2: Strategy Research

```python
# 1. Load and prepare data
reader = DataReader("var/journals")
aggregator = DataAggregator()

df = reader.read_ohlcv(symbol="ATOM/USDT", timeframe="1h", ...)
df = aggregator.add_indicators(df, ["sma_20", "rsi_14", "bbands_20"])

# 2. Backtest strategy (using your backtesting framework)
# ... run backtest ...

# 3. Analyze results
fills_df = reader.read_fills(strategy_id="my_strategy", ...)
positions_df = reader.read_positions(portfolio_id="main", ...)

analyzer = PerformanceAnalyzer(fills_df, positions_df)
trade_stats = analyzer.analyze_trade_distribution()
drawdowns = analyzer.analyze_drawdowns()

# 4. Export for further analysis
exporter = DataExporter(reader)
exporter.export_fills_to_csv(
    strategy_id="my_strategy",
    start_ts=start_ts,
    end_ts=end_ts,
    output_path="analysis/fills.csv"
)
```

### Workflow 3: Multi-Strategy Comparison

```python
# 1. Load backtest results
import json
from backtest.contracts import BacktestResult

results = {}
for strategy_file in ["strategy_a.json", "strategy_b.json", "strategy_c.json"]:
    with open(f"var/backtest/{strategy_file}") as f:
        data = json.load(f)
        # Parse into BacktestResult objects
        # ... (see compare_backtests in cli.py for example)

# 2. Compare strategies
comparison = StrategyComparison(results)

# 3. Generate comparison report
metrics_df = comparison.compare_metrics()
print("\nMetrics Comparison:")
print(metrics_df.to_string())

# 4. Identify divergence periods
divergences = comparison.identify_divergence_periods(threshold=0.05)
print(f"\nFound {len(divergences)} divergence periods")

# 5. Statistical testing
for strategy_a in results.keys():
    for strategy_b in results.keys():
        if strategy_a < strategy_b:
            sig = comparison.statistical_significance(strategy_a, strategy_b)
            print(f"{strategy_a} vs {strategy_b}: p-value={sig['p_value']:.4f}")

# 6. Visualize (in Jupyter)
helper = NotebookHelper()
fig = helper.compare_equity_curves(results, normalize=True)
fig = helper.display_metrics_heatmap(results)
```

## API Reference

See individual module documentation for detailed API references:

- `research.data_reader` — DataReader class
- `research.aggregator` — DataAggregator class
- `research.performance` — PerformanceAnalyzer class
- `research.comparison` — StrategyComparison class
- `research.notebook_helpers` — NotebookHelper class
- `research.export` — DataExporter class
- `research.validator` — DataValidator class
- `research.cli` — Command-line interface

## Best Practices

### 1. Data Loading

- Always specify explicit time ranges to avoid loading too much data
- Use the appropriate format: `"pandas"` for analysis, `"arrow"` for large datasets
- Check data quality before analysis using `DataValidator`

### 2. Performance Analysis

- Calculate metrics on clean data (after validation)
- Use appropriate resampling frequencies for time series analysis
- Consider transaction costs and slippage in performance calculations

### 3. Strategy Comparison

- Normalize equity curves when comparing strategies with different capital
- Use statistical significance tests to validate performance differences
- Examine divergence periods to understand when strategies behave differently

### 4. Export and Sharing

- Use Parquet with compression for large datasets
- Use CSV for compatibility with Excel and other tools
- Use JSON for backtest results and reports

### 5. Jupyter Notebooks

- Use NotebookHelper for quick visualizations
- Export data to files for reproducibility
- Document analysis steps and assumptions

## Troubleshooting

### Issue: No data returned from DataReader

**Cause:** Time range or symbol mismatch

**Solution:**
```python
# Check available data first
from pathlib import Path

journal_dir = Path("var/journals")
ohlcv_files = list(journal_dir.glob("ohlcv.*.ndjson*"))
print(f"Found {len(ohlcv_files)} OHLCV files")

# Or use CLI
# python -m research.cli list-data
```

### Issue: Validation shows many gaps

**Cause:** Data collection was interrupted or timeframe parsing is incorrect

**Solution:**
- Check that data collection was running continuously
- Verify timeframe matches the data files (1m, 5m, 1h, etc.)
- Gaps during market closures (weekends) are normal for some markets

### Issue: PerformanceAnalyzer returns empty results

**Cause:** Column name mismatch or empty DataFrames

**Solution:**
```python
# Check DataFrame structure
print("Fills columns:", fills_df.columns.tolist())
print("Positions columns:", positions_df.columns.tolist())
print("Fills shape:", fills_df.shape)
print("Positions shape:", positions_df.shape)
```

## Additional Resources

- See `notebooks/` directory for example Jupyter notebooks
- See `tests/` directory for usage examples
- Refer to module docstrings for detailed parameter descriptions
