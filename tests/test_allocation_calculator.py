"""Tests for allocation calculator."""

from __future__ import annotations

from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioConfig, StrategyAllocation


def test_allocation_calculator_initialization() -> None:
    """Test AllocationCalculator initialization."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    assert calculator.config == config


def test_calculate_targets_simple() -> None:
    """Test calculating target allocations with simple weights."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)
    targets = calculator.calculate_targets()

    assert len(targets) == 2
    assert abs(targets["strategy_a"] - 60000.0) < 0.01
    assert abs(targets["strategy_b"] - 40000.0) < 0.01


def test_calculate_targets_with_min_max_constraints() -> None:
    """Test calculating targets with min/max weight constraints."""
    allocations = (
        StrategyAllocation(
            strategy_id="strategy_a",
            target_weight=0.6,
            min_weight=0.5,
            max_weight=0.7,
        ),
        StrategyAllocation(
            strategy_id="strategy_b",
            target_weight=0.4,
            min_weight=0.3,
            max_weight=0.5,
        ),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)
    targets = calculator.calculate_targets()

    # Targets should respect min/max constraints
    assert 50000.0 <= targets["strategy_a"] <= 70000.0
    assert 30000.0 <= targets["strategy_b"] <= 50000.0


def test_calculate_targets_ignores_disabled_strategies() -> None:
    """Test that disabled strategies are excluded from targets."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.5, enabled=True),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.5, enabled=True),
        StrategyAllocation(strategy_id="strategy_c", target_weight=0.2, enabled=False),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)
    targets = calculator.calculate_targets()

    # Only enabled strategies should have targets
    assert len(targets) == 2
    assert "strategy_a" in targets
    assert "strategy_b" in targets
    assert "strategy_c" not in targets


def test_calculate_targets_normalization() -> None:
    """Test that targets sum to total_capital after normalization."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)
    targets = calculator.calculate_targets()

    # Sum should equal total_capital
    total = sum(targets.values())
    assert abs(total - 100000.0) < 0.01


def test_calculate_drift_zero_drift() -> None:
    """Test drift calculation with zero drift."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 60000.0, "strategy_b": 40000.0}
    target = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    drift = calculator.calculate_drift(current, target)

    assert abs(drift["strategy_a"]) < 0.01
    assert abs(drift["strategy_b"]) < 0.01


def test_calculate_drift_positive_drift() -> None:
    """Test drift calculation with positive drift."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 66000.0, "strategy_b": 40000.0}  # strategy_a +10%
    target = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    drift = calculator.calculate_drift(current, target)

    assert abs(drift["strategy_a"] - 10.0) < 0.01  # +10% drift
    assert abs(drift["strategy_b"]) < 0.01


def test_calculate_drift_negative_drift() -> None:
    """Test drift calculation with negative drift."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 54000.0, "strategy_b": 40000.0}  # strategy_a -10%
    target = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    drift = calculator.calculate_drift(current, target)

    assert abs(drift["strategy_a"] - (-10.0)) < 0.01  # -10% drift
    assert abs(drift["strategy_b"]) < 0.01


def test_calculate_drift_zero_target() -> None:
    """Test drift calculation when target is zero."""
    allocations = (StrategyAllocation(strategy_id="strategy_a", target_weight=1.0),)

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 100000.0, "strategy_b": 1000.0}  # strategy_b not in target
    target = {"strategy_a": 100000.0}

    drift = calculator.calculate_drift(current, target)

    assert abs(drift["strategy_a"]) < 0.01
    assert drift["strategy_b"] == 100.0  # 100% drift when target is 0 but current > 0


def test_calculate_drift_zero_current_and_target() -> None:
    """Test drift calculation when both current and target are zero."""
    allocations = (StrategyAllocation(strategy_id="strategy_a", target_weight=1.0),)

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 100000.0, "strategy_b": 0.0}
    target = {"strategy_a": 100000.0, "strategy_b": 0.0}

    drift = calculator.calculate_drift(current, target)

    assert drift["strategy_b"] == 0.0  # 0% drift when both are 0


def test_needs_rebalance_below_threshold() -> None:
    """Test rebalance not needed when drift below threshold."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
        rebalance_threshold_pct=10.0,
    )

    calculator = AllocationCalculator(config)

    # Drift of 5% (below 10% threshold)
    drift = {"strategy_a": 5.0, "strategy_b": 0.0}

    # Last rebalance was 1 hour ago (below min_rebalance_interval_sec default of 86400)
    last_rebalance_ts = 0
    current_ts = 3600 * 1_000_000_000  # 1 hour in ns

    needs_rebalance = calculator.needs_rebalance(drift, last_rebalance_ts, current_ts)

    assert needs_rebalance is False


def test_needs_rebalance_above_threshold() -> None:
    """Test rebalance needed when drift above threshold."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
        rebalance_threshold_pct=10.0,
    )

    calculator = AllocationCalculator(config)

    # Drift of 15% (above 10% threshold)
    drift = {"strategy_a": 15.0, "strategy_b": 0.0}

    last_rebalance_ts = 0
    current_ts = 3600 * 1_000_000_000  # 1 hour in ns

    needs_rebalance = calculator.needs_rebalance(drift, last_rebalance_ts, current_ts)

    assert needs_rebalance is True


def test_needs_rebalance_time_elapsed() -> None:
    """Test rebalance needed when min interval elapsed."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
        rebalance_threshold_pct=10.0,
        min_rebalance_interval_sec=86400,  # 1 day
    )

    calculator = AllocationCalculator(config)

    # Drift of 5% (below threshold)
    drift = {"strategy_a": 5.0, "strategy_b": 0.0}

    # Last rebalance was 2 days ago (above min_rebalance_interval_sec)
    last_rebalance_ts = 0
    current_ts = 2 * 86400 * 1_000_000_000  # 2 days in ns

    needs_rebalance = calculator.needs_rebalance(drift, last_rebalance_ts, current_ts)

    assert needs_rebalance is True


def test_needs_rebalance_negative_drift() -> None:
    """Test rebalance with negative drift (uses absolute value)."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
        rebalance_threshold_pct=10.0,
    )

    calculator = AllocationCalculator(config)

    # Negative drift of -15% (absolute value above threshold)
    drift = {"strategy_a": -15.0, "strategy_b": 0.0}

    last_rebalance_ts = 0
    current_ts = 3600 * 1_000_000_000

    needs_rebalance = calculator.needs_rebalance(drift, last_rebalance_ts, current_ts)

    assert needs_rebalance is True


def test_get_rebalance_deltas_positive_deltas() -> None:
    """Test calculating positive rebalance deltas."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 50000.0, "strategy_b": 40000.0}
    target = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    deltas = calculator.get_rebalance_deltas(current, target)

    assert abs(deltas["strategy_a"] - 10000.0) < 0.01  # Need +10k
    assert abs(deltas["strategy_b"]) < 0.01  # No change


def test_get_rebalance_deltas_negative_deltas() -> None:
    """Test calculating negative rebalance deltas."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 70000.0, "strategy_b": 40000.0}
    target = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    deltas = calculator.get_rebalance_deltas(current, target)

    assert abs(deltas["strategy_a"] - (-10000.0)) < 0.01  # Need -10k
    assert abs(deltas["strategy_b"]) < 0.01  # No change


def test_get_rebalance_deltas_missing_current() -> None:
    """Test rebalance deltas when strategy missing from current."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    current = {"strategy_a": 60000.0}  # strategy_b missing
    target = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    deltas = calculator.get_rebalance_deltas(current, target)

    assert abs(deltas["strategy_a"]) < 0.01
    assert abs(deltas["strategy_b"] - 40000.0) < 0.01  # Need to add 40k


def test_validate_allocations_valid() -> None:
    """Test validation of valid allocations."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    valid_allocations = {"strategy_a": 60000.0, "strategy_b": 40000.0}

    is_valid, error = calculator.validate_allocations(valid_allocations)

    assert is_valid is True
    assert error == ""


def test_validate_allocations_missing_strategy() -> None:
    """Test validation fails when strategy is missing."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    invalid_allocations = {"strategy_a": 60000.0}  # Missing strategy_b

    is_valid, error = calculator.validate_allocations(invalid_allocations)

    assert is_valid is False
    assert "Missing allocations" in error


def test_validate_allocations_wrong_total() -> None:
    """Test validation fails when total != total_capital."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.6),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    invalid_allocations = {
        "strategy_a": 60000.0,
        "strategy_b": 30000.0,
    }  # Total = 90k, not 100k

    is_valid, error = calculator.validate_allocations(invalid_allocations)

    assert is_valid is False
    assert "!= total_capital" in error


def test_validate_allocations_below_min() -> None:
    """Test validation fails when allocation below min_weight."""
    allocations = (
        StrategyAllocation(
            strategy_id="strategy_a",
            target_weight=0.6,
            min_weight=0.5,
        ),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    invalid_allocations = {
        "strategy_a": 40000.0,  # Below min_weight of 0.5 (50k)
        "strategy_b": 60000.0,
    }

    is_valid, error = calculator.validate_allocations(invalid_allocations)

    assert is_valid is False
    assert "< min" in error


def test_validate_allocations_above_max() -> None:
    """Test validation fails when allocation above max_weight."""
    allocations = (
        StrategyAllocation(
            strategy_id="strategy_a",
            target_weight=0.6,
            max_weight=0.7,
        ),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.4),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    invalid_allocations = {
        "strategy_a": 80000.0,  # Above max_weight of 0.7 (70k)
        "strategy_b": 20000.0,
    }

    is_valid, error = calculator.validate_allocations(invalid_allocations)

    assert is_valid is False
    assert "> max" in error


def test_validate_allocations_ignores_disabled() -> None:
    """Test validation ignores disabled strategies."""
    allocations = (
        StrategyAllocation(strategy_id="strategy_a", target_weight=0.5, enabled=True),
        StrategyAllocation(strategy_id="strategy_b", target_weight=0.5, enabled=True),
        StrategyAllocation(strategy_id="strategy_c", target_weight=0.2, enabled=False),
    )

    config = PortfolioConfig(
        portfolio_id="portfolio_1",
        allocations=allocations,
        total_capital=100000.0,
    )

    calculator = AllocationCalculator(config)

    # Only include enabled strategies
    valid_allocations = {"strategy_a": 50000.0, "strategy_b": 50000.0}

    is_valid, error = calculator.validate_allocations(valid_allocations)

    assert is_valid is True
    assert error == ""
