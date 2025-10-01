"""Tests for the portfolio backtest engine."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

import pytest

from backtest.contracts import BacktestConfig, BacktestResult
from backtest.engine import BacktestEngine
from backtest.portfolio_engine import PortfolioBacktestEngine, PortfolioBacktestResult
from core.contracts import OrderIntent
from portfolio.contracts import PortfolioConfig, StrategyAllocation
from strategies.base import StrategyBase


class StubStrategy(StrategyBase):
    """Strategy emitting simple buy/sell intents based on price thresholds."""

    def __init__(self, strategy_id: str, symbol: str, fixed_qty: float) -> None:
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.fixed_qty = fixed_qty

    def on_event(self, event: dict[str, object]) -> Iterator[OrderIntent]:
        price = float(cast(float, event.get("close", 0.0)))

        if price < 90:
            yield OrderIntent(
                id="intent",
                ts_local_ns=0,
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                side="buy",
                type="market",
                qty=self.fixed_qty,
                limit_price=None,
            )
        elif price > 110:
            yield OrderIntent(
                id="intent",
                ts_local_ns=0,
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                side="sell",
                type="market",
                qty=self.fixed_qty,
                limit_price=None,
            )


class StubBacktestEngine(BacktestEngine):
    def __init__(self, config: BacktestConfig, equity_delta: float) -> None:
        self.config = config
        self._equity_curve = [
            (config.start_ts, config.initial_capital),
            (config.end_ts, config.initial_capital + equity_delta),
        ]

    def run(self) -> BacktestResult:
        final_capital = self._equity_curve[-1][1]
        total_return_pct = (
            (final_capital - self.config.initial_capital) / self.config.initial_capital
        ) * 100.0
        return BacktestResult(
            strategy_id=self.config.strategy_id,
            symbol=self.config.symbol,
            start_ts=self.config.start_ts,
            end_ts=self.config.end_ts,
            initial_capital=self.config.initial_capital,
            final_capital=final_capital,
            total_return_pct=total_return_pct,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            num_trades=2,
            win_rate=0.5,
            profit_factor=1.2,
            equity_curve=self._equity_curve,
        )


@pytest.mark.parametrize(
    "equity_deltas",
    [
        {"alpha": 1_000.0, "beta": 2_000.0},
    ],
)
def test_portfolio_backtest_engine_aggregates_results(
    tmp_path: Path, equity_deltas: Mapping[str, float]
) -> None:
    config = PortfolioConfig(
        portfolio_id="portfolio-test",
        total_capital=100_000.0,
        allocations=(
            StrategyAllocation(strategy_id="alpha", target_weight=0.5),
            StrategyAllocation(strategy_id="beta", target_weight=0.5),
        ),
        allow_fractional=True,
    )

    strategies: Mapping[str, StrategyBase] = {
        sid: StubStrategy(strategy_id=sid, symbol="ATOM/USDT", fixed_qty=1.0)
        for sid in equity_deltas
    }

    def engine_factory(
        config: BacktestConfig, strategy: StrategyBase, _: Path
    ) -> StubBacktestEngine:
        delta = equity_deltas[config.strategy_id]
        return StubBacktestEngine(config, delta)

    engine = PortfolioBacktestEngine(
        portfolio_config=config,
        strategies=strategies,
        journal_dir=tmp_path,
        engine_factory=engine_factory,
    )

    result = engine.run(start_ts=0, end_ts=1_000)
    assert isinstance(result, PortfolioBacktestResult)
    assert set(result.per_strategy.keys()) == set(equity_deltas.keys())

    expected_final = sum(
        config.total_capital * alloc.target_weight + equity_deltas[alloc.strategy_id]
        for alloc in config.allocations
    )
    assert pytest.approx(result.final_capital, rel=1e-6) == expected_final
    assert pytest.approx(result.metrics["total_return_pct"], rel=1e-6) == result.total_return_pct
