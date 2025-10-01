"""Tests for portfolio HTML report generation."""

from __future__ import annotations

from pathlib import Path

from backtest.contracts import BacktestResult
from backtest.portfolio_engine import PortfolioBacktestResult
from portfolio.report import generate_portfolio_report


def _portfolio_result() -> PortfolioBacktestResult:
    return PortfolioBacktestResult(
        portfolio_id="test_portfolio",
        start_ts=0,
        end_ts=1_000_000_000,
        initial_capital=100_000.0,
        final_capital=110_000.0,
        total_return_pct=10.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=4.0,
        equity_curve=[(0, 100_000.0), (1_000_000_000, 110_000.0)],
        metrics={
            "total_return_pct": 10.0,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 4.0,
        },
        per_strategy={
            "alpha": BacktestResult(
                strategy_id="alpha",
                symbol="ATOM/USDT",
                start_ts=0,
                end_ts=1_000_000_000,
                initial_capital=50_000.0,
                final_capital=55_000.0,
                total_return_pct=10.0,
                sharpe_ratio=1.2,
                max_drawdown_pct=5.0,
                num_trades=10,
                win_rate=0.6,
                profit_factor=1.3,
                equity_curve=[(0, 50_000.0), (1_000_000_000, 55_000.0)],
            ),
            "beta": BacktestResult(
                strategy_id="beta",
                symbol="BTC/USDT",
                start_ts=0,
                end_ts=1_000_000_000,
                initial_capital=50_000.0,
                final_capital=55_000.0,
                total_return_pct=10.0,
                sharpe_ratio=1.8,
                max_drawdown_pct=3.0,
                num_trades=12,
                win_rate=0.65,
                profit_factor=1.4,
                equity_curve=[(0, 50_000.0), (1_000_000_000, 55_000.0)],
            ),
        },
    )


def test_generate_portfolio_report(tmp_path: Path) -> None:
    result = _portfolio_result()
    per_strategy_metrics = {
        sid: {
            "total_return_pct": res.total_return_pct,
            "sharpe_ratio": res.sharpe_ratio,
        }
        for sid, res in result.per_strategy.items()
    }

    allocation_history = [
        (0, {"alpha": 0.6, "beta": 0.4}),
        (500_000_000, {"alpha": 0.5, "beta": 0.5}),
        (1_000_000_000, {"alpha": 0.55, "beta": 0.45}),
    ]

    rebalances = [{"ts": "2025-01-01", "reason": "drift", "alpha": "-5%", "beta": "+5%"}]

    output_path = tmp_path / "portfolio_report.html"
    generate_portfolio_report(
        result=result,
        per_strategy_metrics=per_strategy_metrics,
        allocation_history=allocation_history,
        rebalance_events=rebalances,
        output_path=output_path,
    )

    content = output_path.read_text(encoding="utf-8")
    assert "Portfolio Report" in content
    assert "Equity Curve" in content
    assert "alpha" in content and "beta" in content
    assert "drift" in content
