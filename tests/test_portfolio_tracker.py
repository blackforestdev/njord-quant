"""Tests for the portfolio tracker."""

from __future__ import annotations

from core.contracts import FillEvent
from portfolio.contracts import PortfolioConfig, StrategyAllocation
from portfolio.tracker import PortfolioTracker


def _build_config() -> PortfolioConfig:
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.6),
        StrategyAllocation(strategy_id="beta", target_weight=0.4),
    )
    return PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100_000.0,
        allow_fractional=True,
    )


def test_tracker_initial_state() -> None:
    tracker = PortfolioTracker(_build_config(), clock=lambda: 123)

    assert abs(tracker.get_total_equity() - 100_000.0) < 1e-6
    assert abs(tracker.get_strategy_capital("alpha") - 60_000.0) < 1e-6
    assert abs(tracker.get_strategy_capital("beta") - 40_000.0) < 1e-6

    snapshot = tracker.get_snapshot()
    assert snapshot.ts_ns == 123
    assert snapshot.total_equity == tracker.get_total_equity()
    assert snapshot.cash == 100_000.0
    assert snapshot.positions == []


def test_tracker_on_buy_fill_updates_positions() -> None:
    tracker = PortfolioTracker(_build_config())

    fill = FillEvent(
        order_id="order-1",
        symbol="ATOM/USDT",
        side="buy",
        qty=100.0,
        price=100.0,
        ts_fill_ns=1_000,
        fee=10.0,
        meta={"strategy_id": "alpha"},
    )

    tracker.on_fill(fill)

    strategy_capital = tracker.get_strategy_capital("alpha")
    # Capital decreases slightly due to fees.
    assert abs(strategy_capital - 59_990.0) < 1e-6

    snapshot = tracker.get_snapshot()
    assert snapshot.positions
    position = next(pos for pos in snapshot.positions if pos.strategy_id == "alpha")
    assert position.qty == 100.0
    assert position.avg_entry_price == 100.0
    assert position.current_price == 100.0


def test_tracker_on_sell_realizes_pnl() -> None:
    tracker = PortfolioTracker(_build_config())

    buy_fill = FillEvent(
        order_id="order-1",
        symbol="ATOM/USDT",
        side="buy",
        qty=100.0,
        price=100.0,
        ts_fill_ns=1_000,
        fee=0.0,
        meta={"strategy_id": "alpha"},
    )
    tracker.on_fill(buy_fill)

    sell_fill = FillEvent(
        order_id="order-2",
        symbol="ATOM/USDT",
        side="sell",
        qty=40.0,
        price=110.0,
        ts_fill_ns=2_000,
        fee=4.0,
        meta={"strategy_id": "alpha"},
    )
    tracker.on_fill(sell_fill)

    realized = tracker.get_realized_pnl("alpha")
    # (110 - 100) * 40 - 4 fee
    assert abs(realized - 396.0) < 1e-6

    snapshot = tracker.get_snapshot()
    assert snapshot.total_equity > 100_000.0


def test_tracker_requires_strategy_id_meta() -> None:
    tracker = PortfolioTracker(_build_config())

    fill = FillEvent(
        order_id="order-1",
        symbol="ATOM/USDT",
        side="buy",
        qty=10.0,
        price=50.0,
        ts_fill_ns=1_000,
        fee=0.0,
    )

    try:
        tracker.on_fill(fill)
    except ValueError as exc:
        assert "strategy_id" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing strategy_id")


def test_tracker_mark_to_market_updates_snapshot() -> None:
    tracker = PortfolioTracker(_build_config())

    tracker.update_mark_to_market("alpha", "ATOM/USDT", 120.0, ts_ns=5_000)

    snapshot = tracker.get_snapshot()
    # No position so no unrealized PnL, but snapshot should still succeed.
    assert snapshot.ts_ns >= 5_000


def test_tracker_record_rebalance_reflected_in_snapshot() -> None:
    tracker = PortfolioTracker(_build_config(), clock=lambda: 99)
    tracker.record_rebalance(8888)
    snapshot = tracker.get_snapshot()
    assert snapshot.last_rebalance_ts == 8888
