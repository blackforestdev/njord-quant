"""Tests for backtest report generator."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backtest.report import (
    _calculate_drawdown_series,
    _extract_trade_pnls,
    _generate_config_table,
    _generate_metrics_table,
    generate_report,
)


def test_calculate_drawdown_series() -> None:
    """Test drawdown series calculation."""
    equity_curve = [
        (0, 10000.0),
        (1, 11000.0),  # New peak
        (2, 10500.0),  # Drawdown: (11000 - 10500) / 11000 = 4.55%
        (3, 10000.0),  # Drawdown: (11000 - 10000) / 11000 = 9.09%
        (4, 12000.0),  # New peak
    ]

    drawdowns = _calculate_drawdown_series(equity_curve)

    assert len(drawdowns) == 5
    assert drawdowns[0] == 0.0  # At initial peak
    assert drawdowns[1] == 0.0  # New peak
    assert abs(drawdowns[2] - 4.545454545454546) < 0.01  # 4.55% drawdown
    assert abs(drawdowns[3] - 9.090909090909092) < 0.01  # 9.09% drawdown
    assert drawdowns[4] == 0.0  # New peak


def test_calculate_drawdown_series_empty() -> None:
    """Test drawdown series with empty equity curve."""
    drawdowns = _calculate_drawdown_series([])
    assert drawdowns == []


def test_extract_trade_pnls() -> None:
    """Test extracting P&L from trades."""
    trades = [
        {"side": "buy", "qty": 10.0, "price": 100.0},
        {"side": "sell", "qty": 10.0, "price": 110.0},  # +100 PnL
        {"side": "buy", "qty": 10.0, "price": 110.0},
        {"side": "sell", "qty": 10.0, "price": 105.0},  # -50 PnL
    ]

    pnls = _extract_trade_pnls(trades)

    assert len(pnls) == 2
    assert pnls[0] == 100.0
    assert pnls[1] == -50.0


def test_extract_trade_pnls_no_trades() -> None:
    """Test extracting P&L with no trades."""
    pnls = _extract_trade_pnls([])
    assert pnls == [0.0]


def test_extract_trade_pnls_incomplete() -> None:
    """Test extracting P&L with incomplete trade pairs."""
    trades = [
        {"side": "buy", "qty": 10.0, "price": 100.0},
        # No sell
    ]

    pnls = _extract_trade_pnls(trades)
    assert pnls == [0.0]  # No complete pairs


def test_generate_metrics_table() -> None:
    """Test generating metrics table HTML."""
    metrics = {
        "total_return_pct": 25.5,
        "sharpe_ratio": 1.8,
        "max_drawdown_pct": 10.2,
        "num_trades": 42,
    }

    html = _generate_metrics_table(metrics)

    # Check that HTML contains expected elements
    assert "<table>" in html
    assert "Total Return Pct" in html
    assert "25.50%" in html
    assert "Sharpe Ratio" in html
    assert "1.80" in html
    assert "42" in html


def test_generate_config_table() -> None:
    """Test generating config table HTML."""
    config = {
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        "slippage_bps": 5.0,
    }

    html = _generate_config_table(config)

    # Check that HTML contains expected elements
    assert "<table>" in html
    assert "Initial Capital" in html
    assert "10,000.00" in html
    assert "Commission Rate" in html
    assert "0.00" in html


def test_generate_report() -> None:
    """Test generating complete HTML report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        equity_curve = [
            (0, 10000.0),
            (86400_000_000_000, 10500.0),
            (172800_000_000_000, 11000.0),
        ]

        trades = [
            {"side": "buy", "qty": 10.0, "price": 100.0},
            {"side": "sell", "qty": 10.0, "price": 110.0},
        ]

        metrics = {
            "total_return_pct": 10.0,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 5.0,
            "num_trades": 2,
            "win_rate": 1.0,
            "profit_factor": 2.0,
        }

        config = {
            "initial_capital": 10000.0,
            "commission_rate": 0.001,
            "slippage_bps": 5.0,
        }

        generate_report(
            strategy_id="test_strategy",
            symbol="ATOM/USDT",
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            config=config,
            output_path=output_path,
        )

        # Check that file was created
        assert output_path.exists()

        # Read and verify content
        html_content = output_path.read_text()

        # Check for essential elements
        assert "<!DOCTYPE html>" in html_content
        assert "test_strategy" in html_content
        assert "ATOM/USDT" in html_content
        assert "Performance Metrics" in html_content
        assert "Equity Curve" in html_content
        assert "Drawdown" in html_content
        assert "Trade Distribution" in html_content

        # Check for Plotly
        assert "plotly" in html_content.lower()

        # Check for metrics
        assert "10.00%" in html_content  # total return
        assert "1.50" in html_content  # sharpe ratio

        # Check for config
        assert "10,000.00" in html_content  # initial capital


def test_generate_report_creates_directory() -> None:
    """Test that generate_report creates output directory if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "nested" / "dir" / "report.html"

        # Directory doesn't exist yet
        assert not output_path.parent.exists()

        equity_curve = [(0, 10000.0)]
        metrics = {"total_return_pct": 0.0}
        config = {"initial_capital": 10000.0}

        generate_report(
            strategy_id="test",
            symbol="TEST/USDT",
            metrics=metrics,
            equity_curve=equity_curve,
            trades=[],
            config=config,
            output_path=output_path,
        )

        # Directory should now exist
        assert output_path.parent.exists()
        assert output_path.exists()


def test_generate_report_with_negative_returns() -> None:
    """Test report generation with negative returns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        equity_curve = [
            (0, 10000.0),
            (86400_000_000_000, 9500.0),
            (172800_000_000_000, 9000.0),
        ]

        metrics = {
            "total_return_pct": -10.0,
            "sharpe_ratio": -0.5,
            "max_drawdown_pct": 10.0,
            "num_trades": 1,
        }

        config = {"initial_capital": 10000.0}

        generate_report(
            strategy_id="losing_strategy",
            symbol="ATOM/USDT",
            metrics=metrics,
            equity_curve=equity_curve,
            trades=[],
            config=config,
            output_path=output_path,
        )

        assert output_path.exists()

        html_content = output_path.read_text()

        # Check for negative values with proper CSS classes
        assert "negative" in html_content
        assert "-10.00%" in html_content


def test_generate_report_with_many_trades() -> None:
    """Test report generation with many trades."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        # Generate many equity points
        equity_curve = [(i * 86400_000_000_000, 10000.0 + i * 100) for i in range(100)]

        # Generate many trades
        trades = []
        for i in range(50):
            trades.append({"side": "buy", "qty": 10.0, "price": 100.0 + i})
            trades.append({"side": "sell", "qty": 10.0, "price": 105.0 + i})

        metrics = {
            "total_return_pct": 50.0,
            "sharpe_ratio": 2.0,
            "num_trades": 100,
        }

        config = {"initial_capital": 10000.0}

        generate_report(
            strategy_id="active_strategy",
            symbol="ATOM/USDT",
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            config=config,
            output_path=output_path,
        )

        assert output_path.exists()

        html_content = output_path.read_text()
        assert "100" in html_content  # num_trades
