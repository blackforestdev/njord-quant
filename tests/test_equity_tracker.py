"""Tests for equity tracker."""

from __future__ import annotations

import pytest

from backtest.equity_tracker import EquityTracker


@pytest.fixture
def tracker() -> EquityTracker:
    """Create equity tracker with $10,000 initial capital."""
    return EquityTracker(initial_capital=10000.0)


# Basic functionality tests


def test_initial_state(tracker: EquityTracker) -> None:
    """Test tracker initializes correctly."""
    assert tracker.initial_capital == 10000.0
    assert tracker.get_equity_curve() == []
    assert tracker.get_final_equity() == 10000.0
    assert tracker.get_peak_equity() == 10000.0
    assert tracker.get_current_drawdown() == 0.0


def test_record_zero_position_100_percent_cash(tracker: EquityTracker) -> None:
    """Test recording equity with zero position (100% cash)."""
    # All cash, no position
    tracker.record(ts_ns=1000000000, cash=10000.0, positions={})

    curve = tracker.get_equity_curve()
    assert len(curve) == 1
    assert curve[0] == (1000000000, 10000.0)
    assert tracker.get_final_equity() == 10000.0


def test_record_fully_invested_zero_cash(tracker: EquityTracker) -> None:
    """Test recording equity with fully invested position (0% cash)."""
    # No cash, fully invested in ATOM/USDT
    # 100 units at $100 = $10,000 position value
    tracker.record(
        ts_ns=1000000000,
        cash=0.0,
        positions={"ATOM/USDT": (100.0, 100.0)},
    )

    curve = tracker.get_equity_curve()
    assert len(curve) == 1
    assert curve[0] == (1000000000, 10000.0)
    assert tracker.get_final_equity() == 10000.0


def test_record_mixed_cash_and_position(tracker: EquityTracker) -> None:
    """Test recording equity with both cash and position."""
    # $5,000 cash + 50 units at $100 = $10,000 total
    tracker.record(
        ts_ns=1000000000,
        cash=5000.0,
        positions={"ATOM/USDT": (50.0, 100.0)},
    )

    curve = tracker.get_equity_curve()
    assert len(curve) == 1
    assert curve[0] == (1000000000, 10000.0)
    assert tracker.get_final_equity() == 10000.0


def test_record_multiple_positions(tracker: EquityTracker) -> None:
    """Test recording equity with multiple positions."""
    # $2,000 cash + positions in two symbols
    # ATOM: 30 units at $100 = $3,000
    # BTC: 0.1 units at $50,000 = $5,000
    # Total: $2,000 + $3,000 + $5,000 = $10,000
    tracker.record(
        ts_ns=1000000000,
        cash=2000.0,
        positions={
            "ATOM/USDT": (30.0, 100.0),
            "BTC/USDT": (0.1, 50000.0),
        },
    )

    curve = tracker.get_equity_curve()
    assert len(curve) == 1
    assert curve[0] == (1000000000, 10000.0)


# Profitable strategy tests


def test_monotonically_increasing_equity(tracker: EquityTracker) -> None:
    """Test equity curve for profitable strategy."""
    # Simulate profitable trades over time
    tracker.record(ts_ns=1000, cash=10000.0, positions={})  # Start: $10,000
    tracker.record(
        ts_ns=2000, cash=5000.0, positions={"ATOM/USDT": (50.0, 105.0)}
    )  # Buy at $100, now $105
    tracker.record(
        ts_ns=3000, cash=5000.0, positions={"ATOM/USDT": (50.0, 110.0)}
    )  # Price rises to $110
    tracker.record(ts_ns=4000, cash=10500.0, positions={})  # Sell at $110

    curve = tracker.get_equity_curve()
    assert len(curve) == 4
    assert curve[0] == (1000, 10000.0)
    assert curve[1] == (2000, 10250.0)  # $5k cash + $5.25k position
    assert curve[2] == (3000, 10500.0)  # $5k cash + $5.5k position
    assert curve[3] == (4000, 10500.0)  # All cash after sell

    assert tracker.get_final_equity() == 10500.0
    assert tracker.get_peak_equity() == 10500.0


# Drawdown tests


def test_drawdown_scenario(tracker: EquityTracker) -> None:
    """Test equity curve with drawdown."""
    # Simulate peak, then drawdown
    tracker.record(ts_ns=1000, cash=10000.0, positions={})  # Start: $10,000
    tracker.record(ts_ns=2000, cash=0.0, positions={"ATOM/USDT": (100.0, 120.0)})  # Peak: $12,000
    tracker.record(
        ts_ns=3000, cash=0.0, positions={"ATOM/USDT": (100.0, 110.0)}
    )  # Drawdown: $11,000
    tracker.record(
        ts_ns=4000, cash=0.0, positions={"ATOM/USDT": (100.0, 100.0)}
    )  # Further down: $10,000

    curve = tracker.get_equity_curve()
    assert len(curve) == 4
    assert curve[0][1] == 10000.0
    assert curve[1][1] == 12000.0  # Peak
    assert curve[2][1] == 11000.0  # Drawdown
    assert curve[3][1] == 10000.0  # Larger drawdown

    assert tracker.get_peak_equity() == 12000.0
    assert tracker.get_final_equity() == 10000.0

    # Current drawdown from peak: (12000 - 10000) / 12000 * 100 = 16.67%
    drawdown = tracker.get_current_drawdown()
    assert abs(drawdown - 16.666666666666668) < 0.01


def test_zero_drawdown_when_at_peak(tracker: EquityTracker) -> None:
    """Test drawdown is zero when at peak equity."""
    tracker.record(ts_ns=1000, cash=10000.0, positions={})
    tracker.record(ts_ns=2000, cash=12000.0, positions={})  # New peak

    assert tracker.get_current_drawdown() == 0.0


def test_drawdown_recovery(tracker: EquityTracker) -> None:
    """Test drawdown after recovery."""
    # Peak, drawdown, recovery
    tracker.record(ts_ns=1000, cash=10000.0, positions={})
    tracker.record(ts_ns=2000, cash=12000.0, positions={})  # Peak
    tracker.record(ts_ns=3000, cash=9000.0, positions={})  # Drawdown
    tracker.record(ts_ns=4000, cash=12000.0, positions={})  # Recover to peak

    assert tracker.get_current_drawdown() == 0.0  # No drawdown at peak


# Edge cases


def test_negative_equity(tracker: EquityTracker) -> None:
    """Test handling of negative equity (margin call scenario)."""
    # Simulate catastrophic loss
    tracker.record(ts_ns=1000, cash=-5000.0, positions={})

    assert tracker.get_final_equity() == -5000.0


def test_zero_equity(tracker: EquityTracker) -> None:
    """Test handling of zero equity."""
    tracker.record(ts_ns=1000, cash=0.0, positions={})

    assert tracker.get_final_equity() == 0.0
    assert tracker.get_current_drawdown() == 100.0  # 100% drawdown


def test_fractional_quantities(tracker: EquityTracker) -> None:
    """Test equity calculation with fractional quantities."""
    # 0.5 BTC at $50,000 = $25,000
    tracker.record(
        ts_ns=1000,
        cash=0.0,
        positions={"BTC/USDT": (0.5, 50000.0)},
    )

    assert tracker.get_final_equity() == 25000.0


def test_large_equity_values(tracker: EquityTracker) -> None:
    """Test handling of large equity values."""
    large_tracker = EquityTracker(initial_capital=1000000.0)
    large_tracker.record(
        ts_ns=1000,
        cash=500000.0,
        positions={"BTC/USDT": (10.0, 50000.0)},
    )

    assert large_tracker.get_final_equity() == 1000000.0


def test_equity_curve_isolation(tracker: EquityTracker) -> None:
    """Test that get_equity_curve returns a copy."""
    tracker.record(ts_ns=1000, cash=10000.0, positions={})

    curve1 = tracker.get_equity_curve()
    curve1.append((2000, 99999.0))  # Modify copy

    curve2 = tracker.get_equity_curve()
    assert len(curve2) == 1  # Original unchanged
    assert curve2[0] == (1000, 10000.0)
