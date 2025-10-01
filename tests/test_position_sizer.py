"""Tests for the portfolio position sizer."""

from __future__ import annotations

import pytest

from portfolio.contracts import PortfolioConfig, StrategyAllocation
from portfolio.position_sizer import PositionSizer


def _build_config(allow_fractional: bool = False) -> PortfolioConfig:
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.6),
        StrategyAllocation(strategy_id="beta", target_weight=0.4, enabled=True),
    )
    return PortfolioConfig(
        portfolio_id="test_portfolio",
        allocations=allocations,
        total_capital=100_000.0,
        allow_fractional=allow_fractional,
    )


def test_position_size_integer_rounding() -> None:
    """Position sizing rounds down when fractional trades not allowed."""
    config = _build_config(allow_fractional=False)
    sizer = PositionSizer(config)

    size = sizer.calculate_position_size(
        strategy_id="alpha",
        symbol="ATOM/USDT",
        allocated_capital=12_345.0,
        current_price=123.0,
    )

    assert size == 100.0  # floor(12345 / 123)


def test_position_size_fractional_allowed() -> None:
    """Fractional sizing retains precision when allowed."""
    config = _build_config(allow_fractional=True)
    sizer = PositionSizer(config)

    size = sizer.calculate_position_size(
        strategy_id="alpha",
        symbol="ATOM/USDT",
        allocated_capital=1_000.0,
        current_price=333.33,
    )

    assert abs(size - 3.00003) < 1e-5


def test_position_size_applies_risk_multiplier() -> None:
    """Risk multiplier scales the base position size."""
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.6, risk_multiplier=0.5),
        StrategyAllocation(strategy_id="beta", target_weight=0.4),
    )
    config = PortfolioConfig(
        portfolio_id="test_portfolio",
        allocations=allocations,
        total_capital=100_000.0,
    )
    sizer = PositionSizer(config)

    size = sizer.calculate_position_size(
        strategy_id="alpha",
        symbol="ATOM/USDT",
        allocated_capital=20_000.0,
        current_price=100.0,
    )

    assert size == 100.0  # base 200 units * 0.5 risk multiplier


def test_position_size_handles_high_price_without_fractional() -> None:
    """High prices yield zero units when fractional sizing disabled."""
    config = _build_config(allow_fractional=False)
    sizer = PositionSizer(config)

    size = sizer.calculate_position_size(
        strategy_id="alpha",
        symbol="ATOM/USDT",
        allocated_capital=500.0,
        current_price=1_200.0,
    )

    assert size == 0.0


def test_position_size_rejects_disabled_strategy() -> None:
    """Disabled strategies cannot be sized."""
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.0, enabled=False),
        StrategyAllocation(strategy_id="beta", target_weight=1.0),
    )
    config = PortfolioConfig(
        portfolio_id="test_portfolio",
        allocations=allocations,
        total_capital=100_000.0,
    )
    sizer = PositionSizer(config)

    with pytest.raises(ValueError):
        sizer.calculate_position_size(
            strategy_id="alpha",
            symbol="ATOM/USDT",
            allocated_capital=10_000.0,
            current_price=100.0,
        )


def test_position_size_requires_positive_price() -> None:
    """Sizing with non-positive price raises error."""
    config = _build_config()
    sizer = PositionSizer(config)

    with pytest.raises(ValueError):
        sizer.calculate_position_size(
            strategy_id="alpha",
            symbol="ATOM/USDT",
            allocated_capital=10_000.0,
            current_price=0.0,
        )
