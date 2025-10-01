"""Tests for the portfolio rebalancer."""

from __future__ import annotations

from portfolio.allocation import AllocationCalculator
from portfolio.contracts import (
    PortfolioConfig,
    PortfolioSnapshot,
    StrategyAllocation,
    StrategyPosition,
)
from portfolio.position_sizer import PositionSizer
from portfolio.rebalancer import RebalancePlan, Rebalancer


def _build_portfolio_config() -> PortfolioConfig:
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.6),
        StrategyAllocation(strategy_id="beta", target_weight=0.4),
    )
    return PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100_000.0,
        allow_fractional=False,
    )


def _build_snapshot() -> PortfolioSnapshot:
    positions = [
        StrategyPosition(
            strategy_id="alpha",
            symbol="ATOM/USDT",
            qty=700.0,
            avg_entry_price=95.0,
            current_price=100.0,
            unrealized_pnl=3500.0,
            allocated_capital=70_000.0,
        ),
        StrategyPosition(
            strategy_id="beta",
            symbol="BTC/USDT",
            qty=150.0,
            avg_entry_price=90.0,
            current_price=100.0,
            unrealized_pnl=1500.0,
            allocated_capital=15_000.0,
        ),
    ]

    return PortfolioSnapshot(
        ts_ns=1_700_000_000_000_000_000,
        portfolio_id="portfolio_1",
        total_equity=120_000.0,
        cash=30_000.0,
        positions=positions,
        last_rebalance_ts=1_699_999_000_000_000_000,
    )


def test_rebalancer_generates_buy_and_sell_orders() -> None:
    """Rebalancer issues buy/sell orders to reduce drift."""
    config = _build_portfolio_config()
    allocator = AllocationCalculator(config)
    sizer = PositionSizer(config)
    rebalancer = Rebalancer(allocator, sizer, commission_rate=0.001, slippage_rate=0.0)

    snapshot = _build_snapshot()
    prices = {"ATOM/USDT": 100.0, "BTC/USDT": 100.0}

    plan = rebalancer.create_rebalance_plan(snapshot, prices)

    assert isinstance(plan, RebalancePlan)
    assert len(plan.trades) == 2

    trades_by_strategy = {trade.strategy_id: trade for trade in plan.trades}

    sell_trade = trades_by_strategy["alpha"]
    assert sell_trade.side == "sell"
    assert sell_trade.qty == 100.0

    buy_trade = trades_by_strategy["beta"]
    assert buy_trade.side == "buy"
    assert buy_trade.qty == 250.0

    # Drift reduction should be positive
    assert plan.expected_drift_reduction["alpha"] > 0
    assert plan.expected_drift_reduction["beta"] > 0

    # Estimated costs include commission on both trades (0.001 total rate)
    assert abs(plan.estimated_costs - 35.0) < 1e-6


def test_rebalancer_respects_cash_constraints() -> None:
    """Buys are capped by available cash."""
    config = _build_portfolio_config()
    allocator = AllocationCalculator(config)
    sizer = PositionSizer(config)
    rebalancer = Rebalancer(allocator, sizer)

    snapshot = _build_snapshot()
    snapshot.cash = 5_000.0  # limit buy power
    prices = {"ATOM/USDT": 100.0, "BTC/USDT": 100.0}

    plan = rebalancer.create_rebalance_plan(snapshot, prices)

    buy_trade = next(trade for trade in plan.trades if trade.strategy_id == "beta")
    assert buy_trade.qty == 50.0  # 5,000 notional at 100


def test_rebalancer_skips_tiny_trades() -> None:
    """Trades below the minimum threshold are ignored."""
    config = _build_portfolio_config()
    allocator = AllocationCalculator(config)
    sizer = PositionSizer(config)
    rebalancer = Rebalancer(allocator, sizer, min_trade_value=5_000.0)

    snapshot = _build_snapshot()
    # Adjust positions so drift is small
    snapshot.positions[0].qty = 601.0  # ~1% over target
    snapshot.positions[1].qty = 399.0  # ~1% under target
    prices = {"ATOM/USDT": 100.0, "BTC/USDT": 100.0}

    plan = rebalancer.create_rebalance_plan(snapshot, prices)

    assert plan.trades == []
