"""Position sizing utilities for portfolio allocations."""

from __future__ import annotations

import math

from portfolio.contracts import PortfolioConfig, StrategyAllocation


class PositionSizer:
    """Convert capital allocations into executable position sizes."""

    def __init__(self, config: PortfolioConfig) -> None:
        """Initialize position sizer with portfolio configuration."""
        self.config = config

    def calculate_position_size(
        self,
        strategy_id: str,
        symbol: str,
        allocated_capital: float,
        current_price: float,
    ) -> float:
        """Calculate position size (units) for the provided capital allocation."""
        if current_price <= 0:
            raise ValueError("current_price must be positive")

        if allocated_capital <= 0:
            return 0.0

        allocation = self._get_strategy_allocation(strategy_id)
        base_size = allocated_capital / current_price
        size = self.apply_risk_multiplier(base_size, allocation.risk_multiplier)

        size = self._apply_fractional_policy(size)
        # Ensure we never suggest a negative or NaN quantity
        if size <= 0 or math.isnan(size):
            return 0.0

        # Final guard: cap resulting exposure to allocated capital scaled by risk multiplier
        max_notional = allocated_capital * max(allocation.risk_multiplier, 0.0)
        if max_notional <= 0:
            return 0.0

        notional = size * current_price
        if notional > max_notional:
            capped_size = max_notional / current_price
            size = self._apply_fractional_policy(capped_size)
            if size <= 0:
                return 0.0

        return float(size)

    def apply_risk_multiplier(self, base_size: float, risk_multiplier: float) -> float:
        """Apply risk multiplier to a base position size."""
        if risk_multiplier < 0:
            raise ValueError("risk_multiplier must be non-negative")
        return base_size * risk_multiplier

    def _get_strategy_allocation(self, strategy_id: str) -> StrategyAllocation:
        allocation = self.config.get_allocation(strategy_id)
        if allocation is None:
            raise ValueError(f"Strategy '{strategy_id}' not found in portfolio config")
        if not allocation.enabled:
            raise ValueError(f"Strategy '{strategy_id}' is disabled in portfolio config")
        return allocation

    def _apply_fractional_policy(self, size: float) -> float:
        """Apply fractional/integer rounding based on portfolio configuration."""
        if self.config.allow_fractional:
            return round(size, 8)
        return float(math.floor(size))
