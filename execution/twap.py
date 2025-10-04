"""TWAP (Time-Weighted Average Price) execution algorithm.

This module implements TWAP execution strategy that splits orders into equal
slices distributed evenly over time.
"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from core.bus import BusProto
from core.contracts import OrderIntent
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm, ExecutionReport


class TWAPExecutor(BaseExecutor):
    """Time-Weighted Average Price execution algorithm.

    Splits total order into N equal slices distributed evenly over the
    execution duration. Each slice is submitted at regular intervals.

    Attributes:
        strategy_id: Strategy ID for OrderIntent attribution
        slice_count: Number of slices to split the order into
        order_type: Order type (limit or market)
    """

    def __init__(
        self,
        strategy_id: str,
        slice_count: int = 10,
        order_type: Literal["limit", "market"] = "limit",
    ) -> None:
        """Initialize TWAP executor.

        Args:
            strategy_id: Strategy ID for OrderIntent attribution
            slice_count: Number of slices (must be > 0)
            order_type: Order type (limit or market)

        Raises:
            ValueError: If slice_count <= 0
        """
        super().__init__(strategy_id)
        if slice_count <= 0:
            raise ValueError(f"slice_count must be > 0, got {slice_count}")
        self.slice_count = slice_count
        self.order_type = order_type

    async def plan_execution(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Plan TWAP execution as OrderIntents.

        Splits the total order into equal slices distributed evenly over time.
        Each OrderIntent is scheduled at regular intervals.

        Args:
            algo: Execution algorithm configuration

        Returns:
            List of OrderIntent (one per slice)

        Note:
            Each OrderIntent.meta includes:
            - execution_id: Unique execution identifier
            - slice_id: Slice identifier within this execution
            - algo_type: "TWAP"
        """
        # Generate unique execution ID
        execution_id = f"twap_{uuid.uuid4().hex[:8]}"

        # Calculate slice parameters
        slice_qty = algo.total_quantity / self.slice_count
        interval_ns = (algo.duration_seconds * 1_000_000_000) // self.slice_count

        # Current time as base
        start_ts_ns = int(time.time() * 1e9)

        # Get limit price for limit orders
        # Must be provided in params - no fallback to avoid silent failures
        # Production version would fetch current market price from market data service
        limit_price_base: float | None = None
        if self.order_type == "limit":
            if "limit_price" not in algo.params:
                raise ValueError(
                    "limit_price must be provided in algo.params for limit orders. "
                    "Use order_type='market' or provide params={'limit_price': <price>}"
                )
            price = algo.params["limit_price"]
            if not isinstance(price, (int, float)):
                raise TypeError(f"limit_price must be a number, got {type(price).__name__}")
            limit_price_base = float(price)
            if limit_price_base <= 0:
                raise ValueError(f"limit_price must be > 0, got {limit_price_base}")

        # Generate OrderIntents for all slices
        intents: list[OrderIntent] = []
        for i in range(self.slice_count):
            scheduled_ts_ns = start_ts_ns + (i * interval_ns)

            intent = self._create_slice_intent(
                execution_id=execution_id,
                slice_idx=i,
                symbol=algo.symbol,
                side=algo.side,
                quantity=slice_qty,
                scheduled_ts_ns=scheduled_ts_ns,
                limit_price=limit_price_base,
            )
            intents.append(intent)

        # Generate cancel intents for unfilled slices at end of duration
        # These are scheduled after the execution window to clean up any unfilled orders
        end_ts_ns = start_ts_ns + (algo.duration_seconds * 1_000_000_000)
        for i in range(self.slice_count):
            cancel_intent = self._create_cancel_intent(
                execution_id=execution_id,
                slice_idx=i,
                symbol=algo.symbol,
                side=algo.side,
                scheduled_ts_ns=end_ts_ns,
            )
            intents.append(cancel_intent)

        return intents

    def _create_slice_intent(
        self,
        execution_id: str,
        slice_idx: int,
        symbol: str,
        side: Literal["buy", "sell"],
        quantity: float,
        scheduled_ts_ns: int,
        limit_price: float | None,
    ) -> OrderIntent:
        """Create OrderIntent for individual slice.

        Args:
            execution_id: Unique execution identifier
            slice_idx: Slice index (0-based)
            symbol: Trading pair symbol
            side: Order side (buy or sell)
            quantity: Slice quantity
            scheduled_ts_ns: Scheduled execution time (nanoseconds)
            limit_price: Limit price for order (None for market orders)

        Returns:
            OrderIntent with execution metadata packed in meta field
        """
        slice_id = f"{execution_id}_slice_{slice_idx}"

        # Pack execution metadata into meta field for fill tracking
        meta = {
            "execution_id": execution_id,
            "slice_id": slice_id,
            "algo_type": "TWAP",
            "slice_idx": slice_idx,
        }

        return OrderIntent(
            id=slice_id,  # Use slice_id as intent ID for tracking
            ts_local_ns=scheduled_ts_ns,
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            type=self.order_type,
            qty=quantity,
            limit_price=limit_price,
            meta=meta,
        )

    def _create_cancel_intent(
        self,
        execution_id: str,
        slice_idx: int,
        symbol: str,
        side: Literal["buy", "sell"],
        scheduled_ts_ns: int,
    ) -> OrderIntent:
        """Create cancel OrderIntent for a slice.

        Cancel intents are represented as OrderIntent with qty=0 and special
        metadata indicating the cancellation action and target slice.

        Args:
            execution_id: Unique execution identifier
            slice_idx: Slice index to cancel
            symbol: Trading pair symbol
            side: Order side (buy or sell)
            scheduled_ts_ns: When to execute cancellation (nanoseconds)

        Returns:
            OrderIntent representing cancellation request
        """
        slice_id = f"{execution_id}_slice_{slice_idx}"
        cancel_id = f"{slice_id}_cancel"

        # Pack cancellation metadata
        meta = {
            "execution_id": execution_id,
            "slice_id": slice_id,
            "algo_type": "TWAP",
            "slice_idx": slice_idx,
            "action": "cancel",
            "target_slice_id": slice_id,
        }

        return OrderIntent(
            id=cancel_id,
            ts_local_ns=scheduled_ts_ns,
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            type="market",  # Cancel requests use market type
            qty=0.0,  # Zero quantity indicates cancellation
            limit_price=None,
            meta=meta,
        )

    async def _monitor_fills(
        self, bus: BusProto, execution_id: str, total_quantity: float, symbol: str
    ) -> ExecutionReport:
        """Track fills and build execution report.

        Subscribes to fills.new topic and aggregates fills for this execution.

        Args:
            bus: Bus instance for subscribing to fills
            execution_id: Execution ID to filter fills
            total_quantity: Total quantity to execute
            symbol: Trading pair symbol

        Returns:
            ExecutionReport with aggregated fill data

        Note:
            This is a simplified implementation. Production version would
            handle timeouts, cancellations, and error cases.
        """
        filled_quantity = 0.0
        total_fees = 0.0
        weighted_price_sum = 0.0
        slices_completed = 0
        start_ts_ns = int(time.time() * 1e9)

        async for fill in self.track_fills(bus, execution_id):
            filled_quantity += fill.qty
            total_fees += fill.fee
            weighted_price_sum += fill.price * fill.qty
            slices_completed += 1

            # Check if execution complete
            if filled_quantity >= total_quantity:
                break

        # Calculate average fill price
        avg_fill_price = weighted_price_sum / filled_quantity if filled_quantity > 0 else 0.0

        # Determine status
        status: Literal["running", "completed", "cancelled", "failed"] = (
            "completed" if filled_quantity >= total_quantity else "running"
        )

        end_ts_ns = int(time.time() * 1e9) if status == "completed" else None

        return ExecutionReport(
            execution_id=execution_id,
            symbol=symbol,
            total_quantity=total_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=total_quantity - filled_quantity,
            avg_fill_price=avg_fill_price,
            total_fees=total_fees,
            slices_completed=slices_completed,
            slices_total=self.slice_count,
            status=status,
            start_ts_ns=start_ts_ns,
            end_ts_ns=end_ts_ns,
        )
