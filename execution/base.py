"""Execution layer foundations.

This module provides the base classes and protocols for execution algorithms.
All executors must emit OrderIntent events and go through the risk engine,
never calling the broker directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from core.bus import BusProto
from core.contracts import FillEvent, OrderIntent

if TYPE_CHECKING:
    # ExecutionAlgorithm will be defined in Phase 8.1
    # For now, use a placeholder type
    ExecutionAlgorithm = Any


class BaseExecutor(ABC):
    """Base class for execution algorithms.

    CRITICAL ARCHITECTURE:
    - Executors must emit OrderIntent events, NOT call broker directly
    - All OrderIntents go through risk engine for validation
    - Use OrderIntent.meta to pack execution_id and slice_id for fill tracking

    Typical workflow:
    1. Call plan_execution() to generate OrderIntents
    2. Emit OrderIntents to bus (topic: "strat.intent")
    3. Risk engine validates and emits risk decisions
    4. Broker/paper trader executes approved intents
    5. Use track_fills() to monitor execution progress
    """

    def __init__(self, strategy_id: str) -> None:
        """Initialize executor.

        Args:
            strategy_id: Strategy ID for OrderIntent attribution
        """
        self.strategy_id = strategy_id

    @abstractmethod
    async def plan_execution(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Plan execution, return OrderIntents for risk engine.

        CRITICAL: Must pack execution metadata into OrderIntent.meta:
        - execution_id: Unique identifier for this execution
        - slice_id: Identifier for this slice within the execution
        - algo_type: Algorithm type (TWAP, VWAP, etc.)

        Args:
            algo: Execution algorithm configuration (defined in Phase 8.1)

        Returns:
            List of OrderIntents to emit to bus (topic: "strat.intent")

        Note:
            DO NOT call broker directly. Emit OrderIntents and let the
            risk engine validate them.
        """
        ...

    async def track_fills(self, bus: BusProto, execution_id: str) -> AsyncIterator[FillEvent]:
        """Subscribe to fills for this execution.

        Filters fills.new topic for fills matching this execution_id
        by checking FillEvent.meta["execution_id"].

        Args:
            bus: Bus instance for subscribing to fills
            execution_id: Execution ID to filter fills

        Yields:
            FillEvent instances matching this execution

        Example:
            >>> async for fill in executor.track_fills(bus, "exec_123"):
            ...     print(f"Fill: {fill.qty} @ {fill.price}")
        """
        async for msg in bus.subscribe("fills.new"):
            # FillEvent may be packed in "fill" key or directly
            fill_data = msg.get("fill", msg)

            # Reconstruct FillEvent
            fill = FillEvent(
                order_id=fill_data["order_id"],
                symbol=fill_data["symbol"],
                side=fill_data["side"],
                qty=fill_data["qty"],
                price=fill_data["price"],
                ts_fill_ns=fill_data["ts_fill_ns"],
                fee=fill_data.get("fee", 0.0),
                meta=fill_data.get("meta", {}),
            )

            # Filter by execution_id in meta
            if fill.meta.get("execution_id") == execution_id:
                yield fill
