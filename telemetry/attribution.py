"""Performance attribution for tracking strategy contributions to portfolio PnL."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research.data_reader import DataReader


@dataclass
class AttributionReport:
    """Performance attribution report.

    Attributes:
        portfolio_pnl: Total portfolio PnL
        strategy_pnls: PnL by strategy {strategy_id: pnl}
        strategy_returns: Returns by strategy {strategy_id: return_pct}
        strategy_weights: Weights by strategy {strategy_id: weight}
        allocation_effect: Brinson allocation effect {strategy_id: effect}
        selection_effect: Brinson selection effect {strategy_id: effect}
        alpha: Jensen's alpha vs benchmark
        beta: Beta vs benchmark
        sharpe_ratio: Sharpe ratio (risk-adjusted return)
        sortino_ratio: Sortino ratio (downside risk-adjusted)
        start_ts_ns: Attribution period start
        end_ts_ns: Attribution period end
    """

    portfolio_pnl: float
    strategy_pnls: dict[str, float]
    strategy_returns: dict[str, float] = field(default_factory=dict)
    strategy_weights: dict[str, float] = field(default_factory=dict)
    allocation_effect: dict[str, float] = field(default_factory=dict)
    selection_effect: dict[str, float] = field(default_factory=dict)
    alpha: float | None = None
    beta: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    start_ts_ns: int = 0
    end_ts_ns: int = 0


class PerformanceAttribution:
    """Performance attribution calculator.

    Attributes portfolio performance to individual strategies using
    multiple attribution methods (Brinson, factor-based, risk-adjusted).
    """

    def __init__(
        self,
        data_reader: DataReader,
        portfolio_id: str,
    ) -> None:
        """Initialize performance attribution calculator.

        Args:
            data_reader: DataReader for accessing fills and positions
            portfolio_id: Portfolio identifier
        """
        self.data_reader = data_reader
        self.portfolio_id = portfolio_id

    def calculate_attribution(
        self,
        start_ts_ns: int,
        end_ts_ns: int,
        benchmark_returns: list[float] | None = None,
    ) -> AttributionReport:
        """Calculate performance attribution.

        Args:
            start_ts_ns: Attribution period start (nanoseconds)
            end_ts_ns: Attribution period end (nanoseconds)
            benchmark_returns: Optional benchmark returns for alpha/beta

        Returns:
            AttributionReport with strategy contributions
        """
        # Read all fills in period
        fills_df = self.data_reader.read_fills(
            strategy_id=None,
            start_ts=start_ts_ns,
            end_ts=end_ts_ns,
            format="pandas",
        )

        # Calculate PnL per strategy
        strategy_pnls = self._calculate_strategy_pnls(fills_df)
        portfolio_pnl = sum(strategy_pnls.values())

        # Calculate weights
        strategy_weights = self.attribute_pnl(
            portfolio_pnl=portfolio_pnl,
            strategy_pnls=strategy_pnls,
            strategy_weights={},  # Will be calculated
        )

        # Calculate returns (simplified: return = pnl / initial_capital)
        # For now, use equal weighting assumption
        strategy_returns = {
            sid: pnl / 100.0 if portfolio_pnl != 0 else 0.0 for sid, pnl in strategy_pnls.items()
        }

        report = AttributionReport(
            portfolio_pnl=portfolio_pnl,
            strategy_pnls=strategy_pnls,
            strategy_returns=strategy_returns,
            strategy_weights=strategy_weights,
            start_ts_ns=start_ts_ns,
            end_ts_ns=end_ts_ns,
        )

        # Calculate Brinson attribution if we have benchmark
        if benchmark_returns:
            allocation, selection = self._calculate_brinson_attribution(
                strategy_returns=list(strategy_returns.values()),
                strategy_weights=list(strategy_weights.values()),
                benchmark_returns=benchmark_returns,
            )
            report.allocation_effect = dict(zip(strategy_returns.keys(), allocation, strict=False))
            report.selection_effect = dict(zip(strategy_returns.keys(), selection, strict=False))

            # Calculate alpha/beta
            if strategy_returns:
                # Use portfolio returns
                portfolio_returns = [
                    sum(
                        w * r
                        for w, r in zip(
                            strategy_weights.values(), strategy_returns.values(), strict=False
                        )
                    )
                ]
                if portfolio_returns:
                    alpha, beta = self.calculate_alpha_beta(
                        strategy_returns=portfolio_returns * len(benchmark_returns),
                        benchmark_returns=benchmark_returns,
                    )
                    report.alpha = alpha
                    report.beta = beta

        # Calculate risk-adjusted metrics
        if strategy_returns:
            returns_list = list(strategy_returns.values())
            if returns_list:
                report.sharpe_ratio = self._calculate_sharpe(returns_list)
                report.sortino_ratio = self._calculate_sortino(returns_list)

        return report

    def attribute_pnl(
        self,
        portfolio_pnl: float,
        strategy_pnls: dict[str, float],
        strategy_weights: dict[str, float],
    ) -> dict[str, float]:
        """Attribute portfolio PnL to strategies.

        If weights not provided, calculates proportional weights based on PnL.

        Args:
            portfolio_pnl: Total portfolio PnL
            strategy_pnls: PnL by strategy
            strategy_weights: Weights by strategy (or empty dict to calculate)

        Returns:
            Dict mapping strategy_id to weight
        """
        if not strategy_pnls:
            return {}

        # If weights not provided, calculate proportional weights
        if not strategy_weights:
            total_abs_pnl = sum(abs(pnl) for pnl in strategy_pnls.values())
            if total_abs_pnl > 0:
                return {sid: abs(pnl) / total_abs_pnl for sid, pnl in strategy_pnls.items()}
            # Equal weight if all PnLs are zero
            return {sid: 1.0 / len(strategy_pnls) for sid in strategy_pnls}

        return strategy_weights

    def calculate_alpha_beta(
        self,
        strategy_returns: list[float],
        benchmark_returns: list[float],
    ) -> tuple[float, float]:
        """Calculate alpha and beta vs. benchmark.

        Uses linear regression: strategy_return = alpha + beta * benchmark_return

        Args:
            strategy_returns: Strategy returns
            benchmark_returns: Benchmark returns

        Returns:
            (alpha, beta) tuple
        """
        if not strategy_returns or not benchmark_returns:
            return (0.0, 0.0)

        if len(strategy_returns) != len(benchmark_returns):
            # Pad shorter list
            min_len = min(len(strategy_returns), len(benchmark_returns))
            strategy_returns = strategy_returns[:min_len]
            benchmark_returns = benchmark_returns[:min_len]

        if len(strategy_returns) < 2:
            return (0.0, 1.0)

        # Calculate beta using covariance/variance
        mean_strategy = statistics.mean(strategy_returns)
        mean_benchmark = statistics.mean(benchmark_returns)

        covariance = sum(
            (s - mean_strategy) * (b - mean_benchmark)
            for s, b in zip(strategy_returns, benchmark_returns, strict=False)
        ) / len(strategy_returns)

        variance = sum((b - mean_benchmark) ** 2 for b in benchmark_returns) / len(
            benchmark_returns
        )

        beta = covariance / variance if variance > 0 else 1.0
        alpha = mean_strategy - (beta * mean_benchmark)

        return (alpha, beta)

    def _calculate_strategy_pnls(self, fills_df: object) -> dict[str, float]:
        """Calculate PnL per strategy from fills.

        Args:
            fills_df: DataFrame with fills

        Returns:
            Dict mapping strategy_id to realized PnL
        """
        # Import pandas for DataFrame operations
        try:
            import pandas as pd
        except ImportError:
            return {}

        if not isinstance(fills_df, pd.DataFrame) or fills_df.empty:
            return {}

        strategy_pnls: dict[str, float] = {}

        # Group fills by strategy_id
        for _, row in fills_df.iterrows():
            meta = row.get("meta", {})
            if not isinstance(meta, dict):
                continue

            strategy_id = meta.get("strategy_id")
            if not strategy_id:
                continue

            # Calculate fill PnL (simplified: qty * price for buy, -qty * price for sell)
            side = str(row.get("side", "")).lower()
            qty = float(row.get("qty", 0.0))
            price = float(row.get("price", 0.0))

            pnl = qty * price if side == "buy" else -qty * price

            if strategy_id not in strategy_pnls:
                strategy_pnls[strategy_id] = 0.0
            strategy_pnls[strategy_id] += pnl

        return strategy_pnls

    def _calculate_brinson_attribution(
        self,
        strategy_returns: list[float],
        strategy_weights: list[float],
        benchmark_returns: list[float],
    ) -> tuple[list[float], list[float]]:
        """Calculate Brinson attribution (allocation + selection effects).

        Args:
            strategy_returns: Returns by strategy
            strategy_weights: Weights by strategy
            benchmark_returns: Benchmark returns

        Returns:
            (allocation_effects, selection_effects) tuple of lists
        """
        if not strategy_returns or not strategy_weights:
            return ([], [])

        # Assume equal benchmark weights
        n_strategies = len(strategy_returns)
        benchmark_weight = 1.0 / n_strategies if n_strategies > 0 else 0.0
        benchmark_return = statistics.mean(benchmark_returns) if benchmark_returns else 0.0

        allocation_effects = []
        selection_effects = []

        for weight, ret in zip(strategy_weights, strategy_returns, strict=False):
            # Allocation effect: (portfolio_weight - benchmark_weight) * benchmark_return
            allocation = (weight - benchmark_weight) * benchmark_return

            # Selection effect: portfolio_weight * (strategy_return - benchmark_return)
            selection = weight * (ret - benchmark_return)

            allocation_effects.append(allocation)
            selection_effects.append(selection)

        return (allocation_effects, selection_effects)

    def _calculate_sharpe(self, returns: list[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio.

        Args:
            returns: List of returns
            risk_free_rate: Risk-free rate (default 0)

        Returns:
            Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0

        mean_return = statistics.mean(returns)
        std_dev = statistics.stdev(returns)

        if std_dev == 0:
            return 0.0

        return (mean_return - risk_free_rate) / std_dev

    def _calculate_sortino(
        self, returns: list[float], risk_free_rate: float = 0.0, target: float = 0.0
    ) -> float:
        """Calculate Sortino ratio (downside risk-adjusted).

        Args:
            returns: List of returns
            risk_free_rate: Risk-free rate (default 0)
            target: Target return for downside calculation (default 0)

        Returns:
            Sortino ratio
        """
        if len(returns) < 2:
            return 0.0

        mean_return: float = statistics.mean(returns)

        # Calculate downside deviation
        downside_returns = [r - target for r in returns if r < target]
        if not downside_returns:
            return 0.0

        downside_dev = (sum(r**2 for r in downside_returns) / len(downside_returns)) ** 0.5

        if downside_dev == 0:
            return 0.0

        return float((mean_return - risk_free_rate) / downside_dev)
