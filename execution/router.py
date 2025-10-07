"""Smart Order Router for execution algorithm selection.

This module implements intelligent routing logic to select the optimal
execution algorithm based on order characteristics, market conditions,
and historical performance.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Literal, cast

from core.bus import BusProto
from core.contracts import OrderIntent
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm

AlgoType = Literal["TWAP", "VWAP", "Iceberg", "POV"]


def _validate_algo_type(value: str) -> AlgoType:
    allowed: tuple[str, ...] = ("TWAP", "VWAP", "Iceberg", "POV")
    if value not in allowed:
        raise ValueError(f"Unsupported execution algorithm: {value!r}")
    return cast(AlgoType, value)


class SmartOrderRouter:
    """Smart order router for optimal execution algorithm selection.

    The router evaluates order characteristics (size, urgency, symbol) and
    selects the best execution algorithm. It orchestrates execution by
    delegating to the selected executor and publishing resulting OrderIntents
    to the bus.

    CRITICAL ARCHITECTURE:
    - Acts as orchestrator, NOT executor
    - Publishes OrderIntents to bus (no direct broker calls)
    - Executors emit OrderIntents through risk engine flow

    Attributes:
        bus: Bus instance for publishing OrderIntents
        executors: Mapping of algorithm types to executor instances
        performance_tracker: Optional performance tracker for routing optimization
    """

    def __init__(
        self,
        bus: BusProto,
        executors: Mapping[str, BaseExecutor],
        performance_tracker: Any | None = None,
    ) -> None:
        """Initialize smart order router.

        Args:
            bus: Bus instance for publishing OrderIntents
            executors: Mapping of algo_type -> BaseExecutor instance
            performance_tracker: Optional performance tracker (Phase 8.9)

        Raises:
            ValueError: If executors mapping is empty
        """
        if not executors:
            raise ValueError("executors dict must not be empty")

        self.bus = bus
        self.executors = executors
        self.performance_tracker = performance_tracker

    async def route_order(
        self,
        parent_intent: OrderIntent,
        urgency_seconds: int | None = None,
    ) -> str:
        """Route order to optimal execution algorithm.

        Evaluates order characteristics and market conditions to select
        the best execution algorithm, then orchestrates execution by
        delegating to the selected executor.

        Args:
            parent_intent: Parent OrderIntent to execute
            urgency_seconds: Optional urgency constraint (None = normal execution)

        Returns:
            Execution ID for tracking

        Raises:
            ValueError: If selected algorithm not available in executors
        """
        # Get market conditions (simplified for Phase 8.8)
        market_conditions = self._get_market_conditions(parent_intent.symbol)

        # Select optimal algorithm
        algo_type_str = self._select_algorithm(
            parent_intent,
            urgency_seconds,
            market_conditions,
        )
        algo_type = _validate_algo_type(algo_type_str)

        # Verify executor availability
        if algo_type not in self.executors:
            raise ValueError(
                f"Selected algorithm {algo_type!r} not available in executors. "
                f"Available: {list(self.executors.keys())}"
            )

        # Build execution algorithm configuration
        execution_id = f"sor_{uuid.uuid4().hex[:8]}"
        duration_seconds = urgency_seconds or self._default_duration(parent_intent.qty)

        algo = ExecutionAlgorithm(
            algo_type=algo_type,
            symbol=parent_intent.symbol,
            side=parent_intent.side,
            total_quantity=parent_intent.qty,
            duration_seconds=duration_seconds,
            params={
                "parent_intent_id": parent_intent.id,
                "execution_id": execution_id,
            },
        )

        # Orchestrate execution
        await self._orchestrate_execution(
            self.executors[algo_type],
            algo,
            execution_id,
            parent_intent.id,
        )

        return execution_id

    def _select_algorithm(
        self,
        intent: OrderIntent,
        urgency_seconds: int | None,
        market_conditions: dict[str, Any],
    ) -> str:
        """Select best execution algorithm.

        Selection logic:
        1. High urgency (< 60s) → POV (participate in volume)
        2. Large orders (> 10x avg volume) → Iceberg (hide size)
        3. Normal conditions → TWAP (simple time distribution)
        4. Volume-sensitive → VWAP (volume-weighted)

        Performance tracking (Phase 8.9) will enhance this logic
        with historical performance data.

        Args:
            intent: OrderIntent to execute
            urgency_seconds: Optional urgency constraint
            market_conditions: Dict with market data (volume, spread, etc.)

        Returns:
            Algorithm type (TWAP, VWAP, Iceberg, POV)
        """
        # High urgency → POV
        if urgency_seconds is not None and urgency_seconds < 60 and "POV" in self.executors:
            return "POV"

        # Large order relative to volume → Iceberg
        avg_volume = market_conditions.get("avg_volume_1h", 0.0)
        if avg_volume > 0 and intent.qty > avg_volume * 10 and "Iceberg" in self.executors:
            return "Iceberg"

        # Volume-sensitive execution → VWAP
        # TODO(Phase 8.9): Use performance tracker to refine selection
        if market_conditions.get("volume_volatility", 0.0) > 0.5 and "VWAP" in self.executors:
            return "VWAP"

        # Default to TWAP (most robust, works in all conditions)
        if "TWAP" in self.executors:
            return "TWAP"

        # Fallback: Use first available algorithm
        return next(iter(self.executors.keys()))

    async def _orchestrate_execution(
        self,
        executor: BaseExecutor,
        algo: ExecutionAlgorithm,
        execution_id: str,
        parent_intent_id: str,
    ) -> None:
        """Orchestrate execution: plan + publish OrderIntents.

        Delegates planning to the executor, then publishes the resulting
        OrderIntents to the bus for risk engine validation.

        Args:
            executor: Executor instance to delegate planning
            algo: Execution algorithm configuration

        Note:
            OrderIntents are published to "strat.intent" topic for
            risk engine validation. No direct broker calls.
        """
        # Plan execution (get OrderIntents from executor)
        try:
            intents = await executor.plan_execution(algo)
        except Exception as exc:
            # Handle executor failures gracefully
            # TODO(Phase 8.9): Log failure, update performance tracker
            raise RuntimeError(
                f"Executor {type(executor).__name__} failed to plan execution: {exc}"
            ) from exc

        augmented: list[OrderIntent] = []
        for idx, intent in enumerate(intents):
            meta = dict(intent.meta)
            meta.setdefault("execution_id", execution_id)
            meta.setdefault("parent_intent_id", parent_intent_id)
            meta.setdefault("algo_type", algo.algo_type)
            meta.setdefault("slice_idx", idx)
            meta.setdefault("slice_id", f"{execution_id}_slice_{idx}")
            augmented.append(replace(intent, meta=meta))

        # Publish OrderIntents to bus (risk engine flow)
        for intent in augmented:
            await self.bus.publish_json(
                "strat.intent",
                {
                    "intent": {
                        "id": intent.id,
                        "ts_local_ns": intent.ts_local_ns,
                        "strategy_id": intent.strategy_id,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "type": intent.type,
                        "qty": intent.qty,
                        "limit_price": intent.limit_price,
                        "meta": intent.meta,
                    }
                },
            )

    def _get_market_conditions(self, symbol: str) -> dict[str, Any]:
        """Get market conditions for symbol.

        Simplified implementation for Phase 8.8. Future enhancements
        (Phase 8.9+) will integrate with market data services for
        real-time volume, spread, and volatility metrics.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dict with market conditions (simplified)
        """
        # Placeholder: Return default conditions
        # TODO(Phase 8.9): Integrate with market data service
        return {
            "avg_volume_1h": 1000.0,
            "volume_volatility": 0.3,
            "spread_bps": 5.0,
        }

    def _default_duration(self, quantity: float) -> int:
        """Calculate default execution duration based on quantity.

        Simple heuristic: larger orders get longer execution windows.

        Args:
            quantity: Order quantity

        Returns:
            Duration in seconds
        """
        # Base: 5 minutes for typical orders
        # Scale up for larger quantities
        if quantity < 10:
            return 300  # 5 minutes
        elif quantity < 100:
            return 600  # 10 minutes
        else:
            return 900  # 15 minutes
