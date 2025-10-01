"""Risk-adjusted allocation utilities."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioConfig, StrategyAllocation


def _sharpe_ratio(returns: list[float]) -> float:
    if not returns:
        return float("-inf")
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = math.sqrt(variance)
    if std == 0:
        return float("-inf") if mean <= 0 else float("inf")
    return mean / std


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, drawdown)
    return max_dd


@dataclass
class RiskAdjustedAllocator:
    """Adjust base allocations using strategy performance metrics."""

    base_allocator: AllocationCalculator
    lookback_period_days: int = 30
    adjustment_sensitivity: float = 0.1
    max_drawdown_penalty: float = 0.5

    def __post_init__(self) -> None:
        if self.adjustment_sensitivity < 0:
            raise ValueError("adjustment_sensitivity must be non-negative")
        if self.max_drawdown_penalty < 0:
            raise ValueError("max_drawdown_penalty must be non-negative")

    @property
    def config(self) -> PortfolioConfig:
        return self.base_allocator.config

    def calculate_adjusted_allocations(
        self,
        performance_history: Mapping[str, list[float]],
        base_allocations: Mapping[str, float],
    ) -> dict[str, float]:
        """Return adjusted allocations based on performance metrics."""

        scores: dict[str, float] = {}
        min_score = float("inf")

        for alloc in self.config.enabled_allocations():
            history = list(performance_history.get(alloc.strategy_id, []))
            if self.lookback_period_days > 0:
                history = history[-self.lookback_period_days :]

            sharpe = _sharpe_ratio(history)
            drawdown = _max_drawdown(history)

            penalty = 1.0 - min(drawdown * self.max_drawdown_penalty, 0.99)
            raw_score = sharpe * penalty
            scores[alloc.strategy_id] = raw_score
            min_score = min(min_score, raw_score)

        if min_score == float("inf"):
            min_score = 0.0

        adjusted: dict[str, float] = {}
        total_weight = 0.0

        for alloc in self.config.enabled_allocations():
            base_weight = base_allocations.get(alloc.strategy_id, alloc.target_weight)
            score = scores[alloc.strategy_id]
            score = max(score, min_score - 1.0)
            multiplier = 1.0 + self.adjustment_sensitivity * score
            weight = max(base_weight * max(multiplier, 0.0), 0.0)
            adjusted[alloc.strategy_id] = weight
            total_weight += weight

        if total_weight == 0:
            uniform = 1.0 / len(adjusted)
            return {sid: uniform for sid in adjusted}

        # Normalize and enforce min/max bounds
        for alloc in self.config.enabled_allocations():
            weight = adjusted[alloc.strategy_id] / total_weight
            weight = self._clamp_weight(weight, alloc)
            adjusted[alloc.strategy_id] = weight

        # Re-normalize after clamping
        total_weight = sum(adjusted.values())
        if total_weight == 0:
            uniform = 1.0 / len(adjusted)
            return {sid: uniform for sid in adjusted}

        adjusted = {sid: weight / total_weight for sid, weight in adjusted.items()}
        return adjusted

    def _clamp_weight(self, weight: float, allocation: StrategyAllocation) -> float:
        return max(allocation.min_weight, min(allocation.max_weight, weight))
