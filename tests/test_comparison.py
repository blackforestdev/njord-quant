"""Tests for strategy comparison."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from backtest.contracts import BacktestResult
    from research.comparison import StrategyComparison
else:
    pd = pytest.importorskip("pandas")
    from backtest.contracts import BacktestResult
    from research.comparison import StrategyComparison


@pytest.fixture
def sample_backtest_results() -> dict[str, BacktestResult]:
    """Create sample backtest results."""
    # Strategy A: Strong performer
    result_a = BacktestResult(
        strategy_id="strategy_a",
        symbol="ATOM/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=100000.0,
        final_capital=115000.0,
        total_return_pct=15.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=5.0,
        win_rate=0.60,
        profit_factor=2.0,
        num_trades=10,
        equity_curve=[
            (1704067200000000000, 100000.0),
            (1704153600000000000, 105000.0),
            (1704240000000000000, 110000.0),
            (1704326400000000000, 113000.0),
            (1704412800000000000, 115000.0),
        ],
    )

    # Strategy B: Moderate performer
    result_b = BacktestResult(
        strategy_id="strategy_b",
        symbol="ATOM/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=100000.0,
        final_capital=108000.0,
        total_return_pct=8.0,
        sharpe_ratio=1.0,
        max_drawdown_pct=8.0,
        win_rate=0.55,
        profit_factor=1.8,
        num_trades=15,
        equity_curve=[
            (1704067200000000000, 100000.0),
            (1704153600000000000, 102000.0),
            (1704240000000000000, 105000.0),
            (1704326400000000000, 107000.0),
            (1704412800000000000, 108000.0),
        ],
    )

    return {"strategy_a": result_a, "strategy_b": result_b}


def test_strategy_comparison_initialization(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test StrategyComparison initialization."""
    comparison = StrategyComparison(sample_backtest_results)
    assert comparison.strategy_results is not None
    assert len(comparison.strategy_results) == 2


def test_normalize_equity_curves(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test equity curve normalization."""
    comparison = StrategyComparison(sample_backtest_results)
    result = comparison.normalize_equity_curves(target_capital=100000.0)

    assert "strategy_a" in result.columns
    assert "strategy_b" in result.columns
    assert len(result) == 5

    # All curves should start at target_capital
    assert abs(result["strategy_a"].iloc[0] - 100000.0) < 0.01
    assert abs(result["strategy_b"].iloc[0] - 100000.0) < 0.01


def test_normalize_equity_curves_different_initial_capital(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test normalization with different initial capitals."""
    # Modify one result to have different initial capital
    modified_results = sample_backtest_results.copy()
    result_c = BacktestResult(
        strategy_id="strategy_c",
        symbol="ETH/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=50000.0,  # Different initial capital
        final_capital=60000.0,
        total_return_pct=20.0,
        sharpe_ratio=1.8,
        max_drawdown_pct=6.0,
        win_rate=0.65,
        profit_factor=2.2,
        num_trades=12,
        equity_curve=[
            (1704067200000000000, 50000.0),
            (1704153600000000000, 55000.0),
            (1704240000000000000, 58000.0),
            (1704326400000000000, 59000.0),
            (1704412800000000000, 60000.0),
        ],
    )
    modified_results["strategy_c"] = result_c

    comparison = StrategyComparison(modified_results)
    result = comparison.normalize_equity_curves(target_capital=100000.0)

    # All curves should start at target_capital
    assert abs(result["strategy_c"].iloc[0] - 100000.0) < 0.01


def test_normalize_equity_curves_empty() -> None:
    """Test normalization with empty results."""
    comparison = StrategyComparison({})
    result = comparison.normalize_equity_curves()

    assert result.empty


def test_compare_metrics(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test metrics comparison."""
    comparison = StrategyComparison(sample_backtest_results)
    result = comparison.compare_metrics()

    assert len(result) == 2  # Two strategies
    assert "total_return_pct" in result.columns
    assert "sharpe_ratio" in result.columns
    assert "max_drawdown_pct" in result.columns
    assert "win_rate" in result.columns
    assert "num_trades" in result.columns

    # Check values for strategy_a
    assert result.loc["strategy_a", "total_return_pct"] == 15.0
    assert result.loc["strategy_a", "sharpe_ratio"] == 1.5


def test_compare_metrics_empty() -> None:
    """Test metrics comparison with empty results."""
    comparison = StrategyComparison({})
    result = comparison.compare_metrics()

    assert result.empty


def test_identify_divergence_periods(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test divergence period identification."""
    comparison = StrategyComparison(sample_backtest_results)
    result = comparison.identify_divergence_periods(threshold=0.05)

    # Should identify periods where strategies diverge by >5%
    assert isinstance(result, list)
    # Each tuple should have 4 elements
    for period in result:
        assert len(period) == 4
        start_ts, end_ts, outperformer, underperformer = period
        assert isinstance(start_ts, int)
        assert isinstance(end_ts, int)
        assert isinstance(outperformer, str)
        assert isinstance(underperformer, str)


def test_identify_divergence_periods_single_strategy() -> None:
    """Test divergence with single strategy."""
    result_a = BacktestResult(
        strategy_id="strategy_a",
        symbol="ATOM/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=100000.0,
        final_capital=110000.0,
        total_return_pct=10.0,
        sharpe_ratio=1.2,
        max_drawdown_pct=5.0,
        win_rate=0.60,
        profit_factor=1.5,
        num_trades=10,
        equity_curve=[(1704067200000000000, 100000.0), (1704412800000000000, 110000.0)],
    )

    comparison = StrategyComparison({"strategy_a": result_a})
    result = comparison.identify_divergence_periods(threshold=0.1)

    # Should return empty list with single strategy
    assert result == []


def test_statistical_significance_ttest(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test statistical significance with t-test."""
    comparison = StrategyComparison(sample_backtest_results)
    result = comparison.statistical_significance("strategy_a", "strategy_b", method="ttest")

    assert "p_value" in result
    assert "confidence" in result
    assert "mean_diff" in result

    # p_value should be between 0 and 1
    assert 0 <= result["p_value"] <= 1

    # confidence should be between 0 and 100
    assert 0 <= result["confidence"] <= 100

    # mean_diff should be a float
    assert isinstance(result["mean_diff"], float)


def test_statistical_significance_bootstrap(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test statistical significance with bootstrap."""
    comparison = StrategyComparison(sample_backtest_results)
    result = comparison.statistical_significance("strategy_a", "strategy_b", method="bootstrap")

    assert "p_value" in result
    assert "confidence" in result
    assert "mean_diff" in result

    # p_value should be between 0 and 1
    assert 0 <= result["p_value"] <= 1


def test_statistical_significance_missing_strategy(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test statistical significance with missing strategy."""
    comparison = StrategyComparison(sample_backtest_results)
    result = comparison.statistical_significance("strategy_a", "nonexistent", method="ttest")

    # Should return default values
    assert result["p_value"] == 1.0
    assert result["confidence"] == 0.0
    assert result["mean_diff"] == 0.0


def test_statistical_significance_invalid_method(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test statistical significance with invalid method."""
    comparison = StrategyComparison(sample_backtest_results)

    with pytest.raises(ValueError, match="Unsupported method"):
        comparison.statistical_significance("strategy_a", "strategy_b", method="invalid")
