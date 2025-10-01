"""Tests for backtest performance metrics."""

from __future__ import annotations

from backtest.metrics import calculate_metrics

# Golden test data - known equity curves with expected metrics


def test_empty_equity_curve() -> None:
    """Test metrics for empty equity curve."""
    metrics = calculate_metrics(equity_curve=[])

    assert metrics["total_return_pct"] == 0.0
    assert metrics["sharpe_ratio"] == 0.0
    assert metrics["max_drawdown_pct"] == 0.0
    assert metrics["volatility_annual_pct"] == 0.0


def test_single_point_equity_curve() -> None:
    """Test metrics for single point (no returns)."""
    equity_curve = [(1000, 10000.0)]
    metrics = calculate_metrics(equity_curve)

    assert metrics["total_return_pct"] == 0.0
    assert metrics["sharpe_ratio"] == 0.0
    assert metrics["max_drawdown_pct"] == 0.0


def test_flat_equity_curve() -> None:
    """Test metrics for flat equity (no change)."""
    equity_curve = [
        (1000, 10000.0),
        (2000, 10000.0),
        (3000, 10000.0),
    ]
    metrics = calculate_metrics(equity_curve)

    assert metrics["total_return_pct"] == 0.0
    assert metrics["sharpe_ratio"] == 0.0  # Zero volatility
    assert metrics["max_drawdown_pct"] == 0.0


def test_monotonically_increasing_equity() -> None:
    """Test metrics for profitable strategy with no drawdown."""
    # $10k → $11k → $12k (20% total return)
    equity_curve = [
        (0, 10000.0),
        (86400_000_000_000, 11000.0),  # +1 day
        (172800_000_000_000, 12000.0),  # +2 days
    ]
    metrics = calculate_metrics(equity_curve)

    # Total return: (12000 - 10000) / 10000 * 100 = 20%
    assert abs(metrics["total_return_pct"] - 20.0) < 0.01

    # No drawdown
    assert metrics["max_drawdown_pct"] == 0.0
    assert metrics["max_drawdown_duration_days"] == 0.0

    # Sharpe should be positive
    assert metrics["sharpe_ratio"] > 0


def test_drawdown_calculation() -> None:
    """Test max drawdown calculation."""
    # $10k → $12k (peak) → $9k (25% drawdown) → $13k (recovery)
    equity_curve = [
        (0, 10000.0),
        (86400_000_000_000, 12000.0),  # Peak
        (172800_000_000_000, 9000.0),  # Drawdown: (12k - 9k) / 12k = 25%
        (259200_000_000_000, 13000.0),  # Recovery
    ]
    metrics = calculate_metrics(equity_curve)

    # Max drawdown: (12000 - 9000) / 12000 * 100 = 25%
    assert abs(metrics["max_drawdown_pct"] - 25.0) < 0.01

    # Drawdown duration: 1 day (from day 1 to day 2)
    assert abs(metrics["max_drawdown_duration_days"] - 1.0) < 0.01


def test_drawdown_duration() -> None:
    """Test drawdown duration calculation."""
    # Long drawdown period
    day_ns = 86400_000_000_000
    equity_curve = [
        (0, 10000.0),
        (1 * day_ns, 12000.0),  # Peak
        (2 * day_ns, 11000.0),  # Start drawdown
        (3 * day_ns, 10500.0),
        (4 * day_ns, 10000.0),
        (5 * day_ns, 10500.0),
        (6 * day_ns, 11000.0),
        (7 * day_ns, 12000.0),  # Recover to peak
    ]
    metrics = calculate_metrics(equity_curve)

    # Drawdown from day 1 to day 7 = 6 days
    assert abs(metrics["max_drawdown_duration_days"] - 6.0) < 0.1


def test_sharpe_ratio_manual_calculation() -> None:
    """Test Sharpe ratio matches manual calculation."""
    # Simple equity curve with known returns
    equity_curve = [
        (0, 10000.0),
        (86400_000_000_000, 10100.0),  # +1% return
        (172800_000_000_000, 10200.0),  # +0.99% return
        (259200_000_000_000, 10300.0),  # +0.98% return
    ]
    metrics = calculate_metrics(equity_curve)

    # Returns: 0.01, 0.0099, 0.0098
    # Mean: ~0.0099
    # Std: ~0.0001
    # Sharpe: (0.0099 / 0.0001) * sqrt(365) ≈ 1890 (very high, low volatility)
    assert metrics["sharpe_ratio"] > 100  # Should be very high


def test_volatility_calculation() -> None:
    """Test volatility calculation."""
    # High volatility equity curve
    equity_curve = [
        (0, 10000.0),
        (86400_000_000_000, 12000.0),  # +20%
        (172800_000_000_000, 9600.0),  # -20%
        (259200_000_000_000, 11520.0),  # +20%
    ]
    metrics = calculate_metrics(equity_curve)

    # Volatility should be high
    assert metrics["volatility_annual_pct"] > 100


def test_calmar_ratio() -> None:
    """Test Calmar ratio calculation."""
    # 30% return with 10% max drawdown = Calmar of 3.0
    equity_curve = [
        (0, 10000.0),
        (86400_000_000_000, 12000.0),  # +20%
        (172800_000_000_000, 10800.0),  # -10% drawdown from peak
        (259200_000_000_000, 13000.0),  # +30% total return
    ]
    metrics = calculate_metrics(equity_curve)

    # Total return: 30%
    assert abs(metrics["total_return_pct"] - 30.0) < 0.01

    # Max drawdown: (12000 - 10800) / 12000 = 10%
    assert abs(metrics["max_drawdown_pct"] - 10.0) < 0.01

    # Calmar: 30 / 10 = 3.0
    assert abs(metrics["calmar_ratio"] - 3.0) < 0.01


def test_no_trades() -> None:
    """Test metrics with no trade data."""
    equity_curve = [(0, 10000.0), (1000, 11000.0)]
    metrics = calculate_metrics(equity_curve, trades=None)

    assert metrics["win_rate"] == 0.0
    assert metrics["profit_factor"] == 0.0
    assert metrics["avg_win"] == 0.0
    assert metrics["avg_loss"] == 0.0


def test_all_winning_trades() -> None:
    """Test trade stats with all wins."""
    equity_curve = [(0, 10000.0), (1000, 12000.0)]
    trades = [
        {"side": "buy", "qty": 10.0, "price": 100.0, "commission": 1.0},
        {"side": "sell", "qty": 10.0, "price": 110.0, "commission": 1.1},
        {"side": "buy", "qty": 10.0, "price": 110.0, "commission": 1.1},
        {"side": "sell", "qty": 10.0, "price": 120.0, "commission": 1.2},
    ]
    metrics = calculate_metrics(equity_curve, trades=trades)

    # Win rate: 2/2 = 100%
    assert metrics["win_rate"] == 1.0

    # Profit factor: infinite (no losses)
    assert metrics["profit_factor"] == 0.0  # No losses, so 0

    # Avg win: (100 + 100) / 2 = 100
    assert abs(metrics["avg_win"] - 100.0) < 0.01

    # Largest win: 100
    assert abs(metrics["largest_win"] - 100.0) < 0.01


def test_all_losing_trades() -> None:
    """Test trade stats with all losses."""
    equity_curve = [(0, 10000.0), (1000, 8000.0)]
    trades = [
        {"side": "buy", "qty": 10.0, "price": 100.0, "commission": 1.0},
        {"side": "sell", "qty": 10.0, "price": 90.0, "commission": 0.9},
        {"side": "buy", "qty": 10.0, "price": 90.0, "commission": 0.9},
        {"side": "sell", "qty": 10.0, "price": 80.0, "commission": 0.8},
    ]
    metrics = calculate_metrics(equity_curve, trades=trades)

    # Win rate: 0/2 = 0%
    assert metrics["win_rate"] == 0.0

    # Profit factor: 0 (no wins)
    assert metrics["profit_factor"] == 0.0

    # Avg loss: (-100 + -100) / 2 = -100
    assert abs(metrics["avg_loss"] - (-100.0)) < 0.01

    # Largest loss: -100
    assert abs(metrics["largest_loss"] - (-100.0)) < 0.01


def test_mixed_trades() -> None:
    """Test trade stats with wins and losses."""
    equity_curve = [(0, 10000.0), (1000, 11000.0)]
    trades = [
        # Win: buy at 100, sell at 120 = +200
        {"side": "buy", "qty": 10.0, "price": 100.0, "commission": 1.0},
        {"side": "sell", "qty": 10.0, "price": 120.0, "commission": 1.2},
        # Loss: buy at 120, sell at 110 = -100
        {"side": "buy", "qty": 10.0, "price": 120.0, "commission": 1.2},
        {"side": "sell", "qty": 10.0, "price": 110.0, "commission": 1.1},
    ]
    metrics = calculate_metrics(equity_curve, trades=trades)

    # Win rate: 1/2 = 50%
    assert abs(metrics["win_rate"] - 0.5) < 0.01

    # Profit factor: 200 / 100 = 2.0
    assert abs(metrics["profit_factor"] - 2.0) < 0.01

    # Avg win: 200
    assert abs(metrics["avg_win"] - 200.0) < 0.01

    # Avg loss: -100
    assert abs(metrics["avg_loss"] - (-100.0)) < 0.01

    # Largest win: 200
    assert abs(metrics["largest_win"] - 200.0) < 0.01

    # Largest loss: -100
    assert abs(metrics["largest_loss"] - (-100.0)) < 0.01


def test_golden_metrics_buy_hold() -> None:
    """Golden test: Buy and hold strategy."""
    # Buy at $100, hold for 10 days, price rises to $120
    day_ns = 86400_000_000_000
    equity_curve = [
        (0, 10000.0),  # Start
        (1 * day_ns, 10200.0),
        (2 * day_ns, 10400.0),
        (3 * day_ns, 10600.0),
        (4 * day_ns, 10800.0),
        (5 * day_ns, 11000.0),
        (6 * day_ns, 11200.0),
        (7 * day_ns, 11400.0),
        (8 * day_ns, 11600.0),
        (9 * day_ns, 11800.0),
        (10 * day_ns, 12000.0),  # End
    ]
    metrics = calculate_metrics(equity_curve)

    # Total return: 20%
    assert abs(metrics["total_return_pct"] - 20.0) < 0.01

    # No drawdown
    assert metrics["max_drawdown_pct"] == 0.0

    # Positive Sharpe
    assert metrics["sharpe_ratio"] > 0


def test_golden_metrics_volatile_strategy() -> None:
    """Golden test: Volatile strategy with drawdowns."""
    day_ns = 86400_000_000_000
    equity_curve = [
        (0, 10000.0),
        (1 * day_ns, 11000.0),  # +10%
        (2 * day_ns, 10500.0),  # -4.5% (drawdown from peak)
        (3 * day_ns, 12000.0),  # +14.3% (new peak)
        (4 * day_ns, 10800.0),  # -10% (drawdown from peak)
        (5 * day_ns, 13000.0),  # +20.4% (recovery, new peak)
    ]
    metrics = calculate_metrics(equity_curve)

    # Total return: 30%
    assert abs(metrics["total_return_pct"] - 30.0) < 0.01

    # Max drawdown: (12000 - 10800) / 12000 = 10%
    assert abs(metrics["max_drawdown_pct"] - 10.0) < 0.01

    # High volatility
    assert metrics["volatility_annual_pct"] > 50


def test_zero_initial_capital_edge_case() -> None:
    """Test edge case with zero initial capital."""
    equity_curve = [(0, 0.0), (1000, 100.0)]
    metrics = calculate_metrics(equity_curve)

    # Should handle gracefully
    assert metrics["total_return_pct"] == 0.0
