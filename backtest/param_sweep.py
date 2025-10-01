"""Parameter sweep harness for backtest optimization."""

from __future__ import annotations

import csv
import itertools
from pathlib import Path
from typing import Any

from backtest.contracts import BacktestConfig
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from strategies.base import StrategyBase


class ParameterSweep:
    """Run backtests across parameter ranges."""

    def __init__(
        self,
        strategy_class: type[StrategyBase],
        symbol: str,
        start_ts: int,
        end_ts: int,
        initial_capital: float,
        commission_rate: float,
        slippage_bps: float,
        journal_dir: Path,
    ) -> None:
        """Initialize parameter sweep.

        Args:
            strategy_class: Strategy class to instantiate
            symbol: Trading symbol
            start_ts: Start timestamp (epoch ns)
            end_ts: End timestamp (epoch ns)
            initial_capital: Initial capital
            commission_rate: Commission rate
            slippage_bps: Slippage in basis points
            journal_dir: Directory containing OHLCV journals
        """
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps
        self.journal_dir = journal_dir

        # Parameter ranges
        self.param_ranges: dict[str, list[Any]] = {}

    def add_param_range(self, name: str, values: list[Any]) -> None:
        """Add parameter range to sweep.

        Args:
            name: Parameter name
            values: List of values to test
        """
        self.param_ranges[name] = values

    def run(self, sort_by: str = "sharpe_ratio") -> list[dict[str, Any]]:
        """Run parameter sweep across all combinations.

        Args:
            sort_by: Metric to sort results by (default: sharpe_ratio)

        Returns:
            List of result dictionaries, sorted by specified metric
        """
        if not self.param_ranges:
            raise ValueError("No parameter ranges defined")

        # Generate all parameter combinations
        param_names = list(self.param_ranges.keys())
        param_values_lists = [self.param_ranges[name] for name in param_names]
        combinations = list(itertools.product(*param_values_lists))

        results = []

        # Run backtest for each combination
        for combo in combinations:
            params = dict(zip(param_names, combo, strict=True))

            # Create strategy instance with params
            # Note: Assumes strategy accepts params in constructor
            strategy = self.strategy_class(**params)

            # Create backtest config
            config = BacktestConfig(
                symbol=self.symbol,
                strategy_id=strategy.strategy_id,
                start_ts=self.start_ts,
                end_ts=self.end_ts,
                initial_capital=self.initial_capital,
                commission_rate=self.commission_rate,
                slippage_bps=self.slippage_bps,
            )

            # Run backtest
            engine = BacktestEngine(
                config=config,
                strategy=strategy,
                journal_dir=self.journal_dir,
            )

            result = engine.run()

            # Calculate metrics
            metrics = calculate_metrics(
                equity_curve=result.equity_curve,
                trades=engine.trades,
            )

            # Combine params and metrics
            result_dict = {
                **params,
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
                "num_trades": result.num_trades,
                **metrics,
            }

            results.append(result_dict)

        # Sort by specified metric (descending)
        results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

        return results

    def save_results(
        self,
        results: list[dict[str, Any]],
        output_path: Path,
    ) -> None:
        """Save sweep results to CSV file.

        Args:
            results: List of result dictionaries
            output_path: Path to output CSV file
        """
        if not results:
            return

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get all keys from first result
        fieldnames = list(results[0].keys())

        # Write CSV
        with output_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
