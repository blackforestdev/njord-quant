"""Portfolio backtest engine orchestrating multiple strategy runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from backtest.contracts import BacktestConfig, BacktestResult
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioConfig
from strategies.base import StrategyBase


@dataclass(frozen=True)
class PortfolioBacktestResult:
    """Aggregated result for a portfolio backtest run."""

    portfolio_id: str
    start_ts: int
    end_ts: int
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    equity_curve: list[tuple[int, float]]
    metrics: dict[str, float]
    per_strategy: dict[str, BacktestResult]


class PortfolioBacktestEngine:
    """Execute strategy backtests under a shared portfolio configuration."""

    def __init__(
        self,
        portfolio_config: PortfolioConfig,
        strategies: Mapping[str, StrategyBase],
        journal_dir: Path,
        engine_factory: Callable[[BacktestConfig, StrategyBase, Path], BacktestEngine]
        | None = None,
    ) -> None:
        self.config = portfolio_config
        self.strategies = dict(strategies)
        self.journal_dir = journal_dir
        self.allocator = AllocationCalculator(portfolio_config)
        self.engine_factory = engine_factory or self._default_engine_factory

    @staticmethod
    def _default_engine_factory(
        config: BacktestConfig, strategy: StrategyBase, journal_dir: Path
    ) -> BacktestEngine:
        return BacktestEngine(config, strategy, journal_dir)

    def run(self, start_ts: int, end_ts: int) -> PortfolioBacktestResult:
        targets = self.allocator.calculate_targets()
        strategy_results: dict[str, BacktestResult] = {}
        aggregated_equity: dict[int, float] = {}

        for strategy_id, strategy in self.strategies.items():
            capital = targets.get(strategy_id)
            if capital is None:
                continue

            symbol = getattr(strategy, "symbol", strategy_id)
            config = BacktestConfig(
                symbol=symbol,
                strategy_id=strategy_id,
                start_ts=start_ts,
                end_ts=end_ts,
                initial_capital=capital,
                commission_rate=0.0,
                slippage_bps=0.0,
            )

            engine = self.engine_factory(config, strategy, self.journal_dir)
            result = engine.run()
            strategy_results[strategy_id] = result

            for ts, equity in result.equity_curve:
                aggregated_equity[ts] = aggregated_equity.get(ts, 0.0) + equity

        if aggregated_equity:
            equity_curve = sorted(aggregated_equity.items())
        else:
            equity_curve = [
                (start_ts, self.config.total_capital),
                (end_ts, self.config.total_capital),
            ]

        metrics = calculate_metrics(equity_curve)
        final_capital = equity_curve[-1][1]
        total_return_pct = (
            ((final_capital - self.config.total_capital) / self.config.total_capital) * 100.0
            if self.config.total_capital
            else 0.0
        )

        return PortfolioBacktestResult(
            portfolio_id=self.config.portfolio_id,
            start_ts=start_ts,
            end_ts=end_ts,
            initial_capital=self.config.total_capital,
            final_capital=final_capital,
            total_return_pct=total_return_pct,
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            equity_curve=equity_curve,
            metrics=metrics,
            per_strategy=strategy_results,
        )
