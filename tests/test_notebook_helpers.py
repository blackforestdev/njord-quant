"""Tests for Jupyter notebook helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from backtest.contracts import BacktestResult
    from research.notebook_helpers import NotebookHelper
else:
    pd = pytest.importorskip("pandas")
    matplotlib = pytest.importorskip("matplotlib")
    from backtest.contracts import BacktestResult
    from research.notebook_helpers import NotebookHelper


@pytest.fixture
def sample_backtest_result() -> BacktestResult:
    """Create sample backtest result."""
    return BacktestResult(
        strategy_id="test_strategy",
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


@pytest.fixture
def sample_backtest_results() -> dict[str, BacktestResult]:
    """Create sample backtest results for comparison."""
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


def test_notebook_helper_initialization() -> None:
    """Test NotebookHelper initialization."""
    helper = NotebookHelper()
    assert helper is not None


def test_quick_plot_equity(sample_backtest_result: BacktestResult) -> None:
    """Test quick equity plot."""
    helper = NotebookHelper()
    fig = helper.quick_plot_equity(sample_backtest_result)

    assert fig is not None
    # Check that figure has axes
    assert len(fig.axes) > 0


def test_quick_plot_equity_with_title(sample_backtest_result: BacktestResult) -> None:
    """Test quick equity plot with custom title."""
    helper = NotebookHelper()
    fig = helper.quick_plot_equity(sample_backtest_result, title="Custom Title")

    assert fig is not None
    ax = fig.axes[0]
    assert ax.get_title() == "Custom Title"


def test_quick_plot_equity_custom_figsize(sample_backtest_result: BacktestResult) -> None:
    """Test quick equity plot with custom figure size."""
    helper = NotebookHelper()
    fig = helper.quick_plot_equity(sample_backtest_result, figsize=(10, 5))

    assert fig is not None
    # Check figure size (convert inches to approximate match)
    assert abs(fig.get_figwidth() - 10) < 0.1
    assert abs(fig.get_figheight() - 5) < 0.1


def test_quick_plot_equity_empty_curve() -> None:
    """Test quick equity plot with empty equity curve."""
    result = BacktestResult(
        strategy_id="empty_strategy",
        symbol="ATOM/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=100000.0,
        final_capital=100000.0,
        total_return_pct=0.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        num_trades=0,
        equity_curve=[],
    )

    helper = NotebookHelper()
    with pytest.raises(ValueError, match="no equity curve data"):
        helper.quick_plot_equity(result)


def test_quick_summary_table(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test quick summary table generation."""
    helper = NotebookHelper()
    result = helper.quick_summary_table(sample_backtest_results)

    assert len(result) == 2
    assert "Total Return %" in result.columns
    assert "Sharpe Ratio" in result.columns
    assert "Max Drawdown %" in result.columns
    assert "Win Rate" in result.columns
    assert "Num Trades" in result.columns

    # Check strategy_a values
    assert result.loc["strategy_a", "Total Return %"] == 15.0
    assert result.loc["strategy_a", "Sharpe Ratio"] == 1.5


def test_quick_summary_table_empty() -> None:
    """Test quick summary table with empty results."""
    helper = NotebookHelper()
    result = helper.quick_summary_table({})

    assert result.empty


def test_compare_equity_curves(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test equity curve comparison plot."""
    helper = NotebookHelper()
    fig = helper.compare_equity_curves(sample_backtest_results)

    assert fig is not None
    ax = fig.axes[0]
    # Should have at least 2 lines (one per strategy, plus optional baseline)
    assert len(ax.lines) >= 2


def test_compare_equity_curves_no_normalize(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test equity curve comparison without normalization."""
    helper = NotebookHelper()
    fig = helper.compare_equity_curves(sample_backtest_results, normalize=False)

    assert fig is not None
    ax = fig.axes[0]
    assert ax.get_ylabel() == "Equity ($)"


def test_compare_equity_curves_normalized(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test equity curve comparison with normalization."""
    helper = NotebookHelper()
    fig = helper.compare_equity_curves(sample_backtest_results, normalize=True)

    assert fig is not None
    ax = fig.axes[0]
    assert ax.get_ylabel() == "Equity (%)"


def test_compare_equity_curves_custom_title(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test equity curve comparison with custom title."""
    helper = NotebookHelper()
    fig = helper.compare_equity_curves(sample_backtest_results, title="Test Comparison")

    assert fig is not None
    ax = fig.axes[0]
    assert ax.get_title() == "Test Comparison"


def test_compare_equity_curves_empty() -> None:
    """Test equity curve comparison with empty results."""
    helper = NotebookHelper()
    with pytest.raises(ValueError, match="No results to plot"):
        helper.compare_equity_curves({})


def test_display_metrics_heatmap(sample_backtest_results: dict[str, BacktestResult]) -> None:
    """Test metrics heatmap display."""
    helper = NotebookHelper()
    fig = helper.display_metrics_heatmap(sample_backtest_results)

    assert fig is not None
    ax = fig.axes[0]
    # Check that title is set
    assert "Heatmap" in ax.get_title()


def test_display_metrics_heatmap_with_metrics(
    sample_backtest_results: dict[str, BacktestResult],
) -> None:
    """Test metrics heatmap with specific metrics."""
    helper = NotebookHelper()
    fig = helper.display_metrics_heatmap(
        sample_backtest_results, metrics=["total_return_pct", "sharpe_ratio"]
    )

    assert fig is not None


def test_display_metrics_heatmap_empty() -> None:
    """Test metrics heatmap with empty results."""
    helper = NotebookHelper()
    with pytest.raises(ValueError, match="No results to plot"):
        helper.display_metrics_heatmap({})


def test_export_to_csv(sample_backtest_result: BacktestResult, tmp_path: Path) -> None:
    """Test CSV export."""
    helper = NotebookHelper()
    output_file = tmp_path / "equity.csv"

    helper.export_to_csv(sample_backtest_result, str(output_file))

    # Verify file was created
    assert output_file.exists()

    # Read and verify contents
    df = pd.read_csv(output_file)
    assert "timestamp" in df.columns
    assert "equity" in df.columns
    assert len(df) == 5


def test_export_to_csv_empty_curve(tmp_path: Path) -> None:
    """Test CSV export with empty equity curve."""
    result = BacktestResult(
        strategy_id="empty_strategy",
        symbol="ATOM/USDT",
        start_ts=1704067200000000000,
        end_ts=1704412800000000000,
        initial_capital=100000.0,
        final_capital=100000.0,
        total_return_pct=0.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        num_trades=0,
        equity_curve=[],
    )

    helper = NotebookHelper()
    output_file = tmp_path / "empty.csv"

    with pytest.raises(ValueError, match="no equity curve data"):
        helper.export_to_csv(result, str(output_file))


def test_style_dataframe() -> None:
    """Test DataFrame styling."""
    helper = NotebookHelper()

    df = pd.DataFrame(
        {
            "metric1": [1.234, 2.345, 3.456],
            "metric2": [4.567, 5.678, 6.789],
        }
    )

    styled = helper.style_dataframe(df, precision=1)
    assert styled is not None


def test_style_dataframe_with_gradient() -> None:
    """Test DataFrame styling with gradient."""
    helper = NotebookHelper()

    df = pd.DataFrame(
        {
            "metric1": [1.234, 2.345, 3.456],
            "metric2": [4.567, 5.678, 6.789],
        }
    )

    styled = helper.style_dataframe(df, gradient_cols=["metric1"], precision=2)
    assert styled is not None
