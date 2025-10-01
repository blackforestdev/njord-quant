"""Tests for risk-adjusted allocation logic."""

from __future__ import annotations

from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioConfig, StrategyAllocation
from portfolio.risk_adjusted import RiskAdjustedAllocator


def _build_config() -> PortfolioConfig:
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.6, min_weight=0.2, max_weight=0.8),
        StrategyAllocation(strategy_id="beta", target_weight=0.4, min_weight=0.2, max_weight=0.8),
    )
    return PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100_000.0,
    )


def test_adjustments_favor_higher_sharpe() -> None:
    cfg = _build_config()
    allocator = AllocationCalculator(cfg)
    adjuster = RiskAdjustedAllocator(allocator, adjustment_sensitivity=0.5)

    history = {
        "alpha": [0.02, 0.01, 0.03, 0.04],
        "beta": [0.0, -0.01, 0.0, -0.02],
    }
    base = allocator.calculate_targets()
    base_weights = {sid: val / cfg.total_capital for sid, val in base.items()}

    adjusted = adjuster.calculate_adjusted_allocations(history, base_weights)

    assert adjusted["alpha"] > adjusted["beta"]
    total = sum(adjusted.values())
    assert abs(total - 1.0) < 1e-6


def test_drawdown_penalty_reduces_allocation() -> None:
    cfg = _build_config()
    allocator = AllocationCalculator(cfg)
    adjuster = RiskAdjustedAllocator(allocator, adjustment_sensitivity=0.3)

    history = {
        "alpha": [0.02, 0.01, -0.1, -0.1],
        "beta": [0.01, 0.01, 0.01, 0.01],
    }
    base_weights = {
        sid: alloc.target_weight
        for sid, alloc in zip(["alpha", "beta"], cfg.allocations, strict=False)
    }

    adjusted = adjuster.calculate_adjusted_allocations(history, base_weights)
    assert adjusted["alpha"] < base_weights["alpha"]
    assert adjusted["beta"] > base_weights["beta"]


def test_handles_all_negative_returns() -> None:
    cfg = _build_config()
    allocator = AllocationCalculator(cfg)
    adjuster = RiskAdjustedAllocator(allocator)

    history = {
        "alpha": [-0.02, -0.03, -0.01],
        "beta": [-0.01, -0.02, -0.01],
    }
    base_weights = {"alpha": 0.6, "beta": 0.4}

    adjusted = adjuster.calculate_adjusted_allocations(history, base_weights)
    total = sum(adjusted.values())
    assert abs(total - 1.0) < 1e-6
    assert all(weight >= 0.2 for weight in adjusted.values())
