"""Tests for portfolio contracts."""

from __future__ import annotations

import pytest

from portfolio.contracts import (
    PortfolioConfig,
    PortfolioSnapshot,
    StrategyAllocation,
    StrategyPosition,
)


def test_strategy_allocation_valid() -> None:
    """Test creating valid StrategyAllocation."""
    alloc = StrategyAllocation(
        strategy_id="strategy_a",
        target_weight=0.5,
        min_weight=0.3,
        max_weight=0.7,
        enabled=True,
    )

    assert alloc.strategy_id == "strategy_a"
    assert alloc.target_weight == 0.5
    assert alloc.min_weight == 0.3
    assert alloc.max_weight == 0.7
    assert alloc.enabled is True


def test_strategy_allocation_defaults() -> None:
    """Test StrategyAllocation with default values."""
    alloc = StrategyAllocation(
        strategy_id="strategy_b",
        target_weight=0.4,
    )

    assert alloc.min_weight == 0.0
    assert alloc.max_weight == 1.0
    assert alloc.enabled is True


def test_strategy_allocation_invalid_target_weight() -> None:
    """Test StrategyAllocation with invalid target_weight."""
    with pytest.raises(ValueError, match="target_weight must be in"):
        StrategyAllocation(strategy_id="test", target_weight=1.5)

    with pytest.raises(ValueError, match="target_weight must be in"):
        StrategyAllocation(strategy_id="test", target_weight=-0.1)


def test_strategy_allocation_invalid_min_weight() -> None:
    """Test StrategyAllocation with invalid min_weight."""
    with pytest.raises(ValueError, match="min_weight must be in"):
        StrategyAllocation(strategy_id="test", target_weight=0.5, min_weight=-0.1)

    with pytest.raises(ValueError, match="min_weight must be in"):
        StrategyAllocation(strategy_id="test", target_weight=0.5, min_weight=1.5)


def test_strategy_allocation_invalid_max_weight() -> None:
    """Test StrategyAllocation with invalid max_weight."""
    with pytest.raises(ValueError, match="max_weight must be in"):
        StrategyAllocation(strategy_id="test", target_weight=0.5, max_weight=-0.1)

    with pytest.raises(ValueError, match="max_weight must be in"):
        StrategyAllocation(strategy_id="test", target_weight=0.5, max_weight=1.5)


def test_strategy_allocation_min_greater_than_target() -> None:
    """Test StrategyAllocation with min_weight > target_weight."""
    with pytest.raises(ValueError, match=r"min_weight.*must be <= target_weight"):
        StrategyAllocation(strategy_id="test", target_weight=0.3, min_weight=0.5)


def test_strategy_allocation_target_greater_than_max() -> None:
    """Test StrategyAllocation with target_weight > max_weight."""
    with pytest.raises(ValueError, match=r"target_weight.*must be <= max_weight"):
        StrategyAllocation(strategy_id="test", target_weight=0.8, max_weight=0.6)


def test_portfolio_config_valid() -> None:
    """Test creating valid PortfolioConfig."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
        rebalance_threshold_pct=5.0,
        min_rebalance_interval_sec=86400,
        allow_fractional=False,
    )

    assert config.portfolio_id == "portfolio_1"
    assert len(config.allocations) == 2
    assert config.total_capital == 100000.0
    assert config.rebalance_threshold_pct == 5.0
    assert config.min_rebalance_interval_sec == 86400
    assert config.allow_fractional is False


def test_portfolio_config_defaults() -> None:
    """Test PortfolioConfig with default values."""
    allocations = (StrategyAllocation(strategy_id="strategy_a", target_weight=1.0),)

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    assert config.rebalance_threshold_pct == 5.0
    assert config.min_rebalance_interval_sec == 86400
    assert config.allow_fractional is False


def test_portfolio_config_invalid_total_capital() -> None:
    """Test PortfolioConfig with invalid total_capital."""
    allocations = (StrategyAllocation(strategy_id="strategy_a", target_weight=1.0),)

    with pytest.raises(ValueError, match="total_capital must be positive"):
        PortfolioConfig(
            portfolio_id="portfolio_1",
            allocations=allocations,
            total_capital=0.0,
        )

    with pytest.raises(ValueError, match="total_capital must be positive"):
        PortfolioConfig(
            portfolio_id="portfolio_1",
            allocations=allocations,
            total_capital=-1000.0,
        )


def test_portfolio_config_invalid_rebalance_threshold() -> None:
    """Test PortfolioConfig with invalid rebalance_threshold_pct."""
    allocations = (StrategyAllocation(strategy_id="strategy_a", target_weight=1.0),)

    with pytest.raises(ValueError, match="rebalance_threshold_pct must be non-negative"):
        PortfolioConfig(
            portfolio_id="portfolio_1",
            allocations=allocations,
            total_capital=100000.0,
            rebalance_threshold_pct=-1.0,
        )


def test_portfolio_config_invalid_min_rebalance_interval() -> None:
    """Test PortfolioConfig with invalid min_rebalance_interval_sec."""
    allocations = (StrategyAllocation(strategy_id="strategy_a", target_weight=1.0),)

    with pytest.raises(ValueError, match="min_rebalance_interval_sec must be non-negative"):
        PortfolioConfig(
            portfolio_id="portfolio_1",
            allocations=allocations,
            total_capital=100000.0,
            min_rebalance_interval_sec=-1,
        )


def test_portfolio_config_weights_not_sum_to_one() -> None:
    """Test PortfolioConfig with weights not summing to 1.0."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.3),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.3),
    )

    with pytest.raises(ValueError, match=r"Sum of enabled target_weights must be ~1\.0"):
        PortfolioConfig(
            portfolio_id="portfolio_1",
            allocations=allocations,
            total_capital=100000.0,
        )


def test_portfolio_config_weights_with_disabled_strategies() -> None:
    """Test PortfolioConfig with disabled strategies excluded from weight sum."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6, enabled=True),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4, enabled=True),
        StrategyAllocation(strategy_id="strategy_c", target_weight=0.2, enabled=False),
    )

    # Should succeed: only enabled weights (0.6 + 0.4 = 1.0)
    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    assert len(config.allocations) == 3


def test_portfolio_config_duplicate_strategy_ids() -> None:
    """Test PortfolioConfig with duplicate strategy IDs."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.5),
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.5),
    )

    with pytest.raises(ValueError, match="Duplicate strategy_id"):
        PortfolioConfig(
            portfolio_id="portfolio_1",
            allocations=allocations,
            total_capital=100000.0,
        )


def test_portfolio_config_get_allocation() -> None:
    """Test PortfolioConfig.get_allocation method."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    alloc_a = config.get_allocation("strategy_a")
    assert alloc_a is not None
    assert alloc_a.strategy_id == "strategy_a"
    assert alloc_a.target_weight == 0.6

    alloc_c = config.get_allocation("strategy_c")
    assert alloc_c is None


def test_portfolio_config_enabled_allocations() -> None:
    """Test PortfolioConfig.enabled_allocations method."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.5, enabled=True),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.3, enabled=False),
        StrategyAllocation(strategy_id="strategy_c", target_weight=0.5, enabled=True),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    enabled = config.enabled_allocations()
    assert len(enabled) == 2
    assert enabled[0].strategy_id == "strategy_a"
    assert enabled[1].strategy_id == "strategy_c"


def test_strategy_position() -> None:
    """Test StrategyPosition creation and properties."""
    pos = StrategyPosition(
        strategy_id="strategy_a",
        symbol="ATOM/USDT",
        qty=100.0,
        avg_entry_price=10.0,
        current_price=11.0,
        unrealized_pnl=100.0,
        allocated_capital=5000.0,
    )

    assert pos.strategy_id == "strategy_a"
    assert pos.symbol == "ATOM/USDT"
    assert pos.qty == 100.0
    assert pos.avg_entry_price == 10.0
    assert pos.current_price == 11.0
    assert pos.unrealized_pnl == 100.0
    assert pos.allocated_capital == 5000.0


def test_strategy_position_market_value() -> None:
    """Test StrategyPosition.market_value property."""
    pos = StrategyPosition(
        strategy_id="strategy_a",
        symbol="ATOM/USDT",
        qty=100.0,
        avg_entry_price=10.0,
        current_price=11.5,
        unrealized_pnl=150.0,
        allocated_capital=5000.0,
    )

    assert pos.market_value == 1150.0  # 100 * 11.5


def test_strategy_position_weight() -> None:
    """Test StrategyPosition.weight property."""
    pos = StrategyPosition(
        strategy_id="strategy_a",
        symbol="ATOM/USDT",
        qty=100.0,
        avg_entry_price=10.0,
        current_price=10.0,
        unrealized_pnl=0.0,
        allocated_capital=5000.0,
    )

    assert pos.weight == 0.2  # 1000 / 5000


def test_strategy_position_weight_zero_capital() -> None:
    """Test StrategyPosition.weight with zero allocated_capital."""
    pos = StrategyPosition(
        strategy_id="strategy_a",
        symbol="ATOM/USDT",
        qty=100.0,
        avg_entry_price=10.0,
        current_price=10.0,
        unrealized_pnl=0.0,
        allocated_capital=0.0,
    )

    assert pos.weight == 0.0


def test_portfolio_snapshot() -> None:
    """Test PortfolioSnapshot creation."""
    snapshot = PortfolioSnapshot(
        ts_ns=1000000000,
        portfolio_id="portfolio_1",
        total_equity=100000.0,
        cash=50000.0,
        positions=[],
        last_rebalance_ts=0,
    )

    assert snapshot.ts_ns == 1000000000
    assert snapshot.portfolio_id == "portfolio_1"
    assert snapshot.total_equity == 100000.0
    assert snapshot.cash == 50000.0
    assert len(snapshot.positions) == 0
    assert snapshot.last_rebalance_ts == 0


def test_portfolio_snapshot_defaults() -> None:
    """Test PortfolioSnapshot with default values."""
    snapshot = PortfolioSnapshot(
        ts_ns=1000000000,
        portfolio_id="portfolio_1",
        total_equity=100000.0,
        cash=50000.0,
    )

    assert snapshot.positions == []
    assert snapshot.last_rebalance_ts == 0


def test_portfolio_snapshot_total_position_value() -> None:
    """Test PortfolioSnapshot.total_position_value property."""
    positions = [
        StrategyPosition(
            strategy_id="strategy_a",
            symbol="ATOM/USDT",
            qty=100.0,
            avg_entry_price=10.0,
            current_price=11.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
        StrategyPosition(
            strategy_id="strategy_b",
            symbol="ETH/USDT",
            qty=50.0,
            avg_entry_price=20.0,
            current_price=22.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
    ]

    snapshot = PortfolioSnapshot(
        ts_ns=1000000000,
        portfolio_id="portfolio_1",
        total_equity=100000.0,
        cash=50000.0,
        positions=positions,
    )

    assert snapshot.total_position_value == 2200.0  # (100*11) + (50*22)


def test_portfolio_snapshot_total_unrealized_pnl() -> None:
    """Test PortfolioSnapshot.total_unrealized_pnl property."""
    positions = [
        StrategyPosition(
            strategy_id="strategy_a",
            symbol="ATOM/USDT",
            qty=100.0,
            avg_entry_price=10.0,
            current_price=11.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
        StrategyPosition(
            strategy_id="strategy_b",
            symbol="ETH/USDT",
            qty=50.0,
            avg_entry_price=20.0,
            current_price=22.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
    ]

    snapshot = PortfolioSnapshot(
        ts_ns=1000000000,
        portfolio_id="portfolio_1",
        total_equity=100000.0,
        cash=50000.0,
        positions=positions,
    )

    assert snapshot.total_unrealized_pnl == 200.0


def test_portfolio_snapshot_get_position() -> None:
    """Test PortfolioSnapshot.get_position method."""
    positions = [
        StrategyPosition(
            strategy_id="strategy_a",
            symbol="ATOM/USDT",
            qty=100.0,
            avg_entry_price=10.0,
            current_price=11.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
        StrategyPosition(
            strategy_id="strategy_b",
            symbol="ETH/USDT",
            qty=50.0,
            avg_entry_price=20.0,
            current_price=22.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
    ]

    snapshot = PortfolioSnapshot(
        ts_ns=1000000000,
        portfolio_id="portfolio_1",
        total_equity=100000.0,
        cash=50000.0,
        positions=positions,
    )

    pos_a = snapshot.get_position("strategy_a", "ATOM/USDT")
    assert pos_a is not None
    assert pos_a.strategy_id == "strategy_a"
    assert pos_a.symbol == "ATOM/USDT"

    pos_c = snapshot.get_position("strategy_c", "BTC/USDT")
    assert pos_c is None


def test_portfolio_snapshot_get_strategy_positions() -> None:
    """Test PortfolioSnapshot.get_strategy_positions method."""
    positions = [
        StrategyPosition(
            strategy_id="strategy_a",
            symbol="ATOM/USDT",
            qty=100.0,
            avg_entry_price=10.0,
            current_price=11.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
        StrategyPosition(
            strategy_id="strategy_a",
            symbol="ETH/USDT",
            qty=50.0,
            avg_entry_price=20.0,
            current_price=22.0,
            unrealized_pnl=100.0,
            allocated_capital=5000.0,
        ),
        StrategyPosition(
            strategy_id="strategy_b",
            symbol="BTC/USDT",
            qty=10.0,
            avg_entry_price=30000.0,
            current_price=31000.0,
            unrealized_pnl=10000.0,
            allocated_capital=50000.0,
        ),
    ]

    snapshot = PortfolioSnapshot(
        ts_ns=1000000000,
        portfolio_id="portfolio_1",
        total_equity=100000.0,
        cash=50000.0,
        positions=positions,
    )

    strategy_a_positions = snapshot.get_strategy_positions("strategy_a")
    assert len(strategy_a_positions) == 2
    assert strategy_a_positions[0].symbol == "ATOM/USDT"
    assert strategy_a_positions[1].symbol == "ETH/USDT"

    strategy_b_positions = snapshot.get_strategy_positions("strategy_b")
    assert len(strategy_b_positions) == 1
    assert strategy_b_positions[0].symbol == "BTC/USDT"

    strategy_c_positions = snapshot.get_strategy_positions("strategy_c")
    assert len(strategy_c_positions) == 0
