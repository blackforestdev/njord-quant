"""POV (Percentage of Volume) execution algorithm.

This module implements POV execution strategy that participates in
market volume at a target rate while monitoring real-time volume.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal

from core.bus import BusProto
from core.contracts import OrderIntent
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm

if TYPE_CHECKING:
    from research.data_reader import DataReader


class POVExecutor(BaseExecutor):
    """Percentage of Volume execution algorithm.

    Participates in market volume at a target rate (e.g., 20%), monitoring
    real-time volume and adjusting slice sizes dynamically.

    Attributes:
        strategy_id: Strategy ID for OrderIntent attribution
        data_reader: DataReader for fetching recent volume data
        target_pov: Target participation rate (default 0.2 = 20%)
        min_volume_threshold: Minimum volume to emit orders (default 1000.0)
    """

    def __init__(
        self,
        strategy_id: str,
        data_reader: DataReader,
        target_pov: float = 0.2,
        min_volume_threshold: float = 1000.0,
    ) -> None:
        """Initialize POV executor.

        Args:
            strategy_id: Strategy ID for OrderIntent attribution
            data_reader: DataReader for volume data
            target_pov: Target participation rate (0 < rate <= 1)
            min_volume_threshold: Minimum volume to emit orders (must be > 0)

        Raises:
            ValueError: If target_pov or min_volume_threshold out of valid range
        """
        super().__init__(strategy_id)
        if not 0 < target_pov <= 1:
            raise ValueError(f"target_pov must be in (0, 1], got {target_pov}")
        if min_volume_threshold <= 0:
            raise ValueError(f"min_volume_threshold must be > 0, got {min_volume_threshold}")

        self.data_reader = data_reader
        self.target_pov = target_pov
        self.min_volume_threshold = min_volume_threshold

    async def plan_execution(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Plan POV execution as OrderIntents.

        Generates initial OrderIntent(s) based on recent volume data.
        Subsequent slices are generated dynamically via _monitor_and_slice.

        Args:
            algo: Execution algorithm configuration

        Returns:
            List with initial OrderIntent (or empty if volume too low)

        Note:
            Each OrderIntent.meta includes:
            - execution_id: Unique execution identifier
            - slice_id: Slice identifier within this execution
            - algo_type: "POV"
            - total_quantity: Total quantity to execute
            - target_pov: Target participation rate
            - measurement_period_seconds: Volume measurement period

        Raises:
            ValueError: If limit_price not provided for limit orders
            TypeError: If limit_price is not a number
        """
        # Generate unique execution ID
        execution_id = f"pov_{uuid.uuid4().hex[:8]}"

        # Get measurement period from params (default 60 seconds)
        measurement_period_seconds = algo.params.get("measurement_period_seconds", 60)
        if not isinstance(measurement_period_seconds, (int, float)):
            raise TypeError(
                f"measurement_period_seconds must be a number, got {type(measurement_period_seconds).__name__}"
            )
        measurement_period_seconds = int(measurement_period_seconds)
        if measurement_period_seconds <= 0:
            raise ValueError(
                f"measurement_period_seconds must be > 0, got {measurement_period_seconds}"
            )

        # Get recent volume to size initial slice
        end_ts_ns = int(time.time() * 1e9)
        start_ts_ns = end_ts_ns - (measurement_period_seconds * 1_000_000_000)

        recent_volume = self._get_recent_volume(
            symbol=algo.symbol,
            start_ts_ns=start_ts_ns,
            end_ts_ns=end_ts_ns,
        )

        # Check if volume meets threshold
        if recent_volume < self.min_volume_threshold:
            # No intent - volume too low
            return []

        # Calculate initial slice size
        remaining_quantity = algo.total_quantity
        time_remaining_ns = algo.duration_seconds * 1_000_000_000

        initial_slice_size = self._calculate_slice_size(
            market_volume=recent_volume,
            remaining_quantity=remaining_quantity,
            time_remaining_ns=time_remaining_ns,
        )

        # Get limit price if needed
        limit_price: float | None = None
        order_type = algo.params.get("order_type", "limit")
        if order_type == "limit":
            if "limit_price" not in algo.params:
                raise ValueError(
                    "limit_price must be provided in algo.params for limit orders. "
                    "Provide params={'limit_price': <price>}"
                )
            price = algo.params["limit_price"]
            if not isinstance(price, (int, float)):
                raise TypeError(f"limit_price must be a number, got {type(price).__name__}")
            limit_price = float(price)
            if limit_price <= 0:
                raise ValueError(f"limit_price must be > 0, got {limit_price}")

        # Create initial OrderIntent
        start_ts_ns = int(time.time() * 1e9)

        intent = self._create_slice_intent(
            execution_id=execution_id,
            slice_idx=0,
            symbol=algo.symbol,
            side=algo.side,
            slice_qty=initial_slice_size,
            total_qty=algo.total_quantity,
            limit_price=limit_price,
            scheduled_ts_ns=start_ts_ns,
            measurement_period_seconds=measurement_period_seconds,
            order_type=order_type,
        )

        return [intent]

    def _get_recent_volume(self, symbol: str, start_ts_ns: int, end_ts_ns: int) -> float:
        """Get recent market volume from historical data.

        Args:
            symbol: Trading pair symbol
            start_ts_ns: Start timestamp (nanoseconds)
            end_ts_ns: End timestamp (nanoseconds)

        Returns:
            Total volume in the period (0.0 if no data)
        """
        try:
            df = self.data_reader.read_trades(
                symbol=symbol,
                start_ts=start_ts_ns,
                end_ts=end_ts_ns,
                format="pandas",
            )

            if df is None or len(df) == 0:
                return 0.0

            # Sum volume (assuming 'amount' or 'qty' column)
            if "amount" in df.columns:
                return float(df["amount"].sum())
            elif "qty" in df.columns:
                return float(df["qty"].sum())
            else:
                return 0.0

        except Exception:
            # Fall back to zero volume on error
            # Production version would log the error
            return 0.0

    def _calculate_slice_size(
        self,
        market_volume: float,
        remaining_quantity: float,
        time_remaining_ns: int,
        total_quantity: float | None = None,
        total_duration_ns: int | None = None,
    ) -> float:
        """Calculate next slice size based on POV target.

        Args:
            market_volume: Market volume in last measurement period
            remaining_quantity: Remaining quantity to execute
            time_remaining_ns: Time remaining in execution window
            total_quantity: Total quantity for execution (for acceleration calc)
            total_duration_ns: Total execution duration (for acceleration calc)

        Returns:
            Slice size to maintain target POV

        Note:
            Accelerates if behind schedule by comparing remaining_quantity
            against expected remaining based on time_remaining_ns.
        """
        # Base slice size: market_volume * target_pov
        base_slice = market_volume * self.target_pov

        # Acceleration logic: if behind schedule, increase slice size
        # Behind schedule = remaining_quantity is too high for time remaining
        if total_quantity is not None and total_duration_ns is not None and total_duration_ns > 0:
            # Calculate expected progress
            time_elapsed_ns = total_duration_ns - time_remaining_ns
            if total_duration_ns > 0:
                expected_progress = time_elapsed_ns / total_duration_ns
                actual_progress = (total_quantity - remaining_quantity) / total_quantity

                # If we're behind (actual < expected), accelerate
                if actual_progress < expected_progress - 0.05:  # 5% tolerance
                    # Acceleration factor based on how far behind
                    lag = expected_progress - actual_progress
                    acceleration_factor = 1.0 + min(lag * 2.0, 1.0)  # Cap at 2x
                    base_slice *= acceleration_factor

        # Cap at remaining quantity
        slice_size = min(base_slice, remaining_quantity)

        return slice_size

    def _create_slice_intent(
        self,
        execution_id: str,
        slice_idx: int,
        symbol: str,
        side: Literal["buy", "sell"],
        slice_qty: float,
        total_qty: float,
        limit_price: float | None,
        scheduled_ts_ns: int,
        measurement_period_seconds: int,
        order_type: Literal["market", "limit"] = "limit",
    ) -> OrderIntent:
        """Create OrderIntent for POV slice.

        Args:
            execution_id: Unique execution identifier
            slice_idx: Slice index (0 for initial, increments with each slice)
            symbol: Trading pair symbol
            side: Order side (buy or sell)
            slice_qty: Slice quantity
            total_qty: Total quantity (for tracking)
            limit_price: Limit price (None for market orders)
            scheduled_ts_ns: Scheduled execution time (nanoseconds)
            measurement_period_seconds: Volume measurement period
            order_type: Order type (limit or market)

        Returns:
            OrderIntent with POV metadata packed in meta field
        """
        slice_id = f"{execution_id}_slice_{slice_idx}"

        # Pack POV metadata into meta field for fill tracking
        meta: dict[str, Any] = {
            "execution_id": execution_id,
            "slice_id": slice_id,
            "algo_type": "POV",
            "slice_idx": slice_idx,
            "total_quantity": total_qty,
            "target_pov": self.target_pov,
            "measurement_period_seconds": measurement_period_seconds,
        }

        return OrderIntent(
            id=slice_id,
            ts_local_ns=scheduled_ts_ns,
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            type=order_type,
            qty=slice_qty,
            limit_price=limit_price,
            meta=meta,
        )

    async def _monitor_volume(self, bus: BusProto, symbol: str) -> float:
        """Monitor real-time market volume.

        Subscribes to market data (trades) and calculates volume in measurement period.

        Args:
            bus: Bus instance for subscribing to market data
            symbol: Trading pair symbol

        Returns:
            Volume in last measurement period

        Note:
            This is a simplified implementation. Production version would
            maintain a sliding window of trades and calculate volume continuously.
        """
        # Simplified: Return 0.0 as placeholder
        # Full implementation would subscribe to "md.trades" topic
        # and maintain sliding window of trades for volume calculation
        return 0.0

    async def _monitor_and_slice(
        self, bus: BusProto, execution_id: str, algo: ExecutionAlgorithm
    ) -> AsyncIterator[OrderIntent]:
        """Monitor volume and yield POV OrderIntents.

        Tracks market volume and fills, yielding new OrderIntents to maintain
        target POV participation rate.

        Args:
            bus: Bus instance for subscribing to market data and fills
            execution_id: Execution ID to filter fills
            algo: Original execution algorithm configuration

        Yields:
            OrderIntent instances for each POV slice

        Note:
            This is a simplified implementation. Production version would
            handle timeouts, volume spikes, and dynamic adjustment.
        """
        # Get params
        measurement_period_seconds = algo.params.get("measurement_period_seconds", 60)
        limit_price = algo.params.get("limit_price")
        order_type = algo.params.get("order_type", "limit")

        # Track fills
        filled_quantity = 0.0
        current_slice_idx = 0
        start_ts_ns = int(time.time() * 1e9)

        async for fill in self.track_fills(bus, execution_id):
            filled_quantity += fill.qty

            # Check if we need more slices
            remaining_quantity = algo.total_quantity - filled_quantity

            if remaining_quantity <= 0.001:  # Small tolerance
                break

            # Get recent volume
            current_ts_ns = int(time.time() * 1e9)
            time_elapsed_ns = current_ts_ns - start_ts_ns
            time_remaining_ns = (algo.duration_seconds * 1_000_000_000) - time_elapsed_ns

            if time_remaining_ns <= 0:
                # Execution window expired
                break

            volume_start_ts = current_ts_ns - (measurement_period_seconds * 1_000_000_000)
            recent_volume = self._get_recent_volume(
                symbol=algo.symbol,
                start_ts_ns=volume_start_ts,
                end_ts_ns=current_ts_ns,
            )

            # Check volume threshold
            if recent_volume < self.min_volume_threshold:
                # Pause - volume too low
                continue

            # Calculate next slice (with acceleration)
            total_duration_ns = algo.duration_seconds * 1_000_000_000
            next_slice_size = self._calculate_slice_size(
                market_volume=recent_volume,
                remaining_quantity=remaining_quantity,
                time_remaining_ns=time_remaining_ns,
                total_quantity=algo.total_quantity,
                total_duration_ns=total_duration_ns,
            )

            # Generate next intent
            current_slice_idx += 1

            next_intent = self._create_slice_intent(
                execution_id=execution_id,
                slice_idx=current_slice_idx,
                symbol=algo.symbol,
                side=algo.side,
                slice_qty=next_slice_size,
                total_qty=algo.total_quantity,
                limit_price=limit_price,
                scheduled_ts_ns=current_ts_ns,
                measurement_period_seconds=measurement_period_seconds,
                order_type=order_type,
            )

            yield next_intent
