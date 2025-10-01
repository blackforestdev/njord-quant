"""Portfolio allocation calculator."""

from __future__ import annotations

from portfolio.contracts import PortfolioConfig


class AllocationCalculator:
    """Calculate target capital allocations per strategy.

    Handles target allocation calculation, drift detection, and rebalance triggers.
    """

    def __init__(self, config: PortfolioConfig) -> None:
        """Initialize allocation calculator.

        Args:
            config: Portfolio configuration
        """
        self.config = config

    def calculate_targets(
        self,
        current_allocations: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Calculate target capital allocations based on weights.

        Args:
            current_allocations: Current capital per strategy (optional, for constraints)

        Returns:
            Dict mapping strategy_id to target capital
        """
        targets: dict[str, float] = {}

        # Calculate target capital for each enabled strategy
        for alloc in self.config.enabled_allocations():
            target_capital = self.config.total_capital * alloc.target_weight

            # Apply min/max weight constraints
            min_capital = self.config.total_capital * alloc.min_weight
            max_capital = self.config.total_capital * alloc.max_weight

            target_capital = max(min_capital, min(target_capital, max_capital))

            targets[alloc.strategy_id] = target_capital

        # Normalize to ensure sum equals total_capital (handle rounding)
        total_allocated = sum(targets.values())
        if total_allocated > 0:
            normalization_factor = self.config.total_capital / total_allocated
            for strategy_id in targets:
                targets[strategy_id] *= normalization_factor

        return targets

    def calculate_drift(
        self,
        current_allocations: dict[str, float],
        target_allocations: dict[str, float],
    ) -> dict[str, float]:
        """Calculate drift from target allocations.

        Drift is calculated as percentage difference from target:
        drift = ((current - target) / target) * 100

        Args:
            current_allocations: Current capital per strategy
            target_allocations: Target capital per strategy

        Returns:
            Dict mapping strategy_id to drift percentage
        """
        drift: dict[str, float] = {}

        # Get all strategy IDs from both current and target
        all_strategy_ids = set(current_allocations.keys()) | set(target_allocations.keys())

        for strategy_id in all_strategy_ids:
            current = current_allocations.get(strategy_id, 0.0)
            target = target_allocations.get(strategy_id, 0.0)

            if target == 0.0:
                # If target is 0, drift is 0 if current is also 0, else 100%
                drift[strategy_id] = 0.0 if current == 0.0 else 100.0
            else:
                drift[strategy_id] = ((current - target) / target) * 100.0

        return drift

    def needs_rebalance(
        self,
        drift: dict[str, float],
        last_rebalance_ts: int,
        current_ts: int,
    ) -> bool:
        """Check if rebalance is needed based on drift and time.

        Rebalance is triggered if:
        1. Any strategy drifts beyond threshold, OR
        2. Minimum rebalance interval has elapsed

        Args:
            drift: Drift percentages per strategy
            last_rebalance_ts: Timestamp of last rebalance (epoch ns)
            current_ts: Current timestamp (epoch ns)

        Returns:
            True if rebalance is needed, False otherwise
        """
        # Check drift threshold
        max_abs_drift = max((abs(d) for d in drift.values()), default=0.0)
        if max_abs_drift >= self.config.rebalance_threshold_pct:
            return True

        # Check time since last rebalance
        time_elapsed_sec = (current_ts - last_rebalance_ts) / 1_000_000_000
        return time_elapsed_sec >= self.config.min_rebalance_interval_sec

    def get_rebalance_deltas(
        self,
        current_allocations: dict[str, float],
        target_allocations: dict[str, float],
    ) -> dict[str, float]:
        """Calculate capital deltas needed to rebalance.

        Positive delta = need to add capital
        Negative delta = need to remove capital

        Args:
            current_allocations: Current capital per strategy
            target_allocations: Target capital per strategy

        Returns:
            Dict mapping strategy_id to capital delta
        """
        deltas: dict[str, float] = {}

        # Get all strategy IDs from both current and target
        all_strategy_ids = set(current_allocations.keys()) | set(target_allocations.keys())

        for strategy_id in all_strategy_ids:
            current = current_allocations.get(strategy_id, 0.0)
            target = target_allocations.get(strategy_id, 0.0)
            deltas[strategy_id] = target - current

        return deltas

    def validate_allocations(
        self,
        allocations: dict[str, float],
    ) -> tuple[bool, str]:
        """Validate that allocations meet portfolio constraints.

        Args:
            allocations: Capital allocations to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check that all enabled strategies are present
        enabled_ids = {alloc.strategy_id for alloc in self.config.enabled_allocations()}
        missing_ids = enabled_ids - allocations.keys()
        if missing_ids:
            return (False, f"Missing allocations for strategies: {missing_ids}")

        # Check that total equals total_capital (with tolerance)
        total_allocated = sum(allocations.get(sid, 0.0) for sid in enabled_ids)
        tolerance = 0.01  # 1 cent tolerance
        if abs(total_allocated - self.config.total_capital) > tolerance:
            return (
                False,
                f"Total allocation {total_allocated} != total_capital {self.config.total_capital}",
            )

        # Check min/max constraints
        for alloc in self.config.enabled_allocations():
            strategy_capital = allocations.get(alloc.strategy_id, 0.0)
            min_capital = self.config.total_capital * alloc.min_weight
            max_capital = self.config.total_capital * alloc.max_weight

            if strategy_capital < min_capital - tolerance:
                return (
                    False,
                    f"Strategy {alloc.strategy_id} capital {strategy_capital} < min {min_capital}",
                )

            if strategy_capital > max_capital + tolerance:
                return (
                    False,
                    f"Strategy {alloc.strategy_id} capital {strategy_capital} > max {max_capital}",
                )

        return (True, "")
