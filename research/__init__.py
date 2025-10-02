"""Research utilities package.

This package provides tools for offline data analysis, backtesting evaluation,
and strategy research.

Main modules:
- data_reader: Load journal data into pandas DataFrames
- aggregator: Resample OHLCV and calculate technical indicators
- performance: Calculate performance metrics from backtest results
- comparison: Compare multiple strategies side-by-side
- notebook_helpers: Jupyter-friendly plotting and display utilities
- export: Export data to CSV, Parquet, and JSON formats
- validator: Validate data quality and detect anomalies
- cli: Command-line interface for common operations

Quick start:
    >>> from research import DataReader
    >>> reader = DataReader("var/journals")
    >>> df = reader.read_ohlcv("ATOM/USDT", "1m", start_ts, end_ts)
"""

from __future__ import annotations

from .aggregator import DataAggregator
from .comparison import StrategyComparison
from .data_reader import DataReader
from .export import DataExporter
from .notebook_helpers import NotebookHelper
from .performance import PerformanceAnalyzer
from .validator import DataValidator

__all__ = [
    "DataAggregator",
    "DataExporter",
    "DataReader",
    "DataValidator",
    "NotebookHelper",
    "PerformanceAnalyzer",
    "StrategyComparison",
]

__version__ = "0.0.1"
