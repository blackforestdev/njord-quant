"""VWAP (Volume-Weighted Average Price) execution algorithm.

This module implements VWAP execution strategy that weights order slices
based on historical volume patterns.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Literal

from core.bus import BusProto
from core.contracts import FillEvent, OrderIntent
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm, ExecutionReport

if TYPE_CHECKING:
    from research.data_reader import DataReader


class VWAPExecutor(BaseExecutor):
    """Volume-Weighted Average Price execution algorithm.

    Weights order slices based on historical volume distribution to minimize
    market impact and track VWAP benchmark.

    Attributes:
        strategy_id: Strategy ID for OrderIntent attribution
        data_reader: DataReader for fetching historical volume data
        lookback_days: Number of days to analyze for volume profile
        slice_count: Number of slices to split the order into
        order_type: Order type (limit or market)
    """

    def __init__(
        self,
        strategy_id: str,
        data_reader: DataReader,
        lookback_days: int = 7,
        slice_count: int = 10,
        order_type: Literal["limit", "market"] = "limit",
    ) -> None:
        """Initialize VWAP executor.

        Args:
            strategy_id: Strategy ID for OrderIntent attribution
            data_reader: DataReader for historical volume data
            lookback_days: Days of historical data to analyze (default: 7)
            slice_count: Number of slices (must be > 0)
            order_type: Order type (limit or market)

        Raises:
            ValueError: If lookback_days <= 0 or slice_count <= 0
        """
        super().__init__(strategy_id)
        if lookback_days <= 0:
            raise ValueError(f"lookback_days must be > 0, got {lookback_days}")
        if slice_count <= 0:
            raise ValueError(f"slice_count must be > 0, got {slice_count}")

        self.data_reader = data_reader
        self.lookback_days = lookback_days
        self.slice_count = slice_count
        self.order_type = order_type

    async def plan_execution(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Plan VWAP execution as OrderIntents.

        Calculates volume profile from historical data and weights slices
        accordingly. Larger slices are scheduled during high-volume periods.

        Args:
            algo: Execution algorithm configuration

        Returns:
            List of OrderIntent (weighted by volume)

        Note:
            Each OrderIntent.meta includes:
            - execution_id: Unique execution identifier
            - slice_id: Slice identifier within this execution
            - algo_type: "VWAP"
        """
        # Generate unique execution ID
        execution_id = f"vwap_{uuid.uuid4().hex[:8]}"

        # Calculate volume profile and benchmark VWAP
        volume_weights, benchmark_vwap = self._calculate_volume_profile(
            symbol=algo.symbol, duration_seconds=algo.duration_seconds
        )

        # Get limit price for limit orders (same validation as TWAP)
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

        # Calculate slice interval
        interval_ns = (algo.duration_seconds * 1_000_000_000) // self.slice_count

        # Current time as base
        start_ts_ns = int(time.time() * 1e9)

        # Generate OrderIntents for all slices
        intents: list[OrderIntent] = []
        for i in range(self.slice_count):
            scheduled_ts_ns = start_ts_ns + (i * interval_ns)
            weight = volume_weights[i]
            slice_qty = algo.total_quantity * weight

            intent = self._create_weighted_intent(
                execution_id=execution_id,
                slice_idx=i,
                symbol=algo.symbol,
                side=algo.side,
                weight=weight,
                total_quantity=algo.total_quantity,
                slice_quantity=slice_qty,
                scheduled_ts_ns=scheduled_ts_ns,
                limit_price=limit_price_base,
                benchmark_vwap=benchmark_vwap,
            )
            intents.append(intent)

        return intents

    def _calculate_volume_profile(
        self, symbol: str, duration_seconds: int
    ) -> tuple[list[float], float | None]:
        """Calculate expected volume distribution and benchmark VWAP from historical data.

        Args:
            symbol: Trading pair symbol
            duration_seconds: Execution duration in seconds

        Returns:
            Tuple of (volume weights summing to 1.0, benchmark VWAP price or None)

        Note:
            Falls back to uniform distribution if:
            - No historical data available
            - Insufficient data for analysis
            - Data read errors
        """
        try:
            # Calculate lookback period
            end_ts_ns = int(time.time() * 1e9)
            start_ts_ns = end_ts_ns - (self.lookback_days * 24 * 60 * 60 * 1_000_000_000)

            # Determine appropriate timeframe based on duration
            # For short durations, use smaller timeframes
            if duration_seconds <= 3600:  # 1 hour or less
                timeframe = "1m"
            elif duration_seconds <= 14400:  # 4 hours or less
                timeframe = "5m"
            else:
                timeframe = "15m"

            # Fetch OHLCV data
            df = self.data_reader.read_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                start_ts=start_ts_ns,
                end_ts=end_ts_ns,
                format="pandas",
            )

            # Check if we have enough data
            if df is None or len(df) < self.slice_count:
                # Fall back to uniform distribution
                return ([1.0 / self.slice_count] * self.slice_count, None)

            # Extract volume and price columns
            volumes = df["volume"].values
            # Use typical price (high + low + close) / 3 for VWAP calculation
            if "high" in df.columns and "low" in df.columns and "close" in df.columns:
                typical_prices = (df["high"] + df["low"] + df["close"]) / 3.0
            elif "close" in df.columns:
                typical_prices = df["close"]
            else:
                # No price data available
                typical_prices = None

            # Calculate benchmark VWAP from historical data
            benchmark_vwap = None
            if typical_prices is not None and len(typical_prices) > 0:
                total_volume = sum(volumes)
                if total_volume > 0:
                    benchmark_vwap = float(sum(typical_prices.values * volumes) / total_volume)

            # Group volumes into slices
            slice_size = len(volumes) // self.slice_count
            slice_volumes = []

            for i in range(self.slice_count):
                start_idx = i * slice_size
                end_idx = (i + 1) * slice_size if i < self.slice_count - 1 else len(volumes)
                slice_vol = sum(volumes[start_idx:end_idx])
                slice_volumes.append(slice_vol)

            # Calculate total volume
            total_volume = sum(slice_volumes)

            # Handle zero volume case
            if total_volume == 0:
                return ([1.0 / self.slice_count] * self.slice_count, benchmark_vwap)

            # Normalize to weights summing to 1.0
            weights = [vol / total_volume for vol in slice_volumes]

            return (weights, benchmark_vwap)

        except Exception:
            # Fall back to uniform distribution on any error
            # Production version would log the error
            return ([1.0 / self.slice_count] * self.slice_count, None)

    def _create_weighted_intent(
        self,
        execution_id: str,
        slice_idx: int,
        symbol: str,
        side: Literal["buy", "sell"],
        weight: float,
        total_quantity: float,
        slice_quantity: float,
        scheduled_ts_ns: int,
        limit_price: float | None,
        benchmark_vwap: float | None,
    ) -> OrderIntent:
        """Create OrderIntent for volume-weighted slice.

        Args:
            execution_id: Unique execution identifier
            slice_idx: Slice index (0-based)
            symbol: Trading pair symbol
            side: Order side (buy or sell)
            weight: Volume weight for this slice (0.0 to 1.0)
            total_quantity: Total quantity to execute
            slice_quantity: Quantity for this slice
            scheduled_ts_ns: Scheduled execution time (nanoseconds)
            limit_price: Limit price for order (None for market orders)
            benchmark_vwap: Historical VWAP benchmark price (None if unavailable)

        Returns:
            OrderIntent with execution metadata packed in meta field
        """
        slice_id = f"{execution_id}_slice_{slice_idx}"

        # Pack execution metadata into meta field for fill tracking
        meta = {
            "execution_id": execution_id,
            "slice_id": slice_id,
            "algo_type": "VWAP",
            "slice_idx": slice_idx,
            "volume_weight": weight,  # Track weight for analysis
            "benchmark_vwap": benchmark_vwap,  # Historical VWAP for comparison
        }

        return OrderIntent(
            id=slice_id,  # Use slice_id as intent ID for tracking
            ts_local_ns=scheduled_ts_ns,
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            type=self.order_type,
            qty=slice_quantity,
            limit_price=limit_price,
            meta=meta,
        )

    async def _monitor_fills(
        self,
        bus: BusProto,
        execution_id: str,
        total_quantity: float,
        symbol: str,
        benchmark_vwap: float | None,
    ) -> ExecutionReport:
        """Track fills and build execution report with VWAP benchmark comparison.

        Subscribes to fills.new topic and aggregates fills for this execution,
        comparing execution VWAP against historical benchmark.

        Args:
            bus: Bus instance for subscribing to fills
            execution_id: Execution ID to filter fills
            total_quantity: Total quantity to execute
            symbol: Trading pair symbol
            benchmark_vwap: Historical VWAP benchmark (None if unavailable)

        Returns:
            ExecutionReport with aggregated fill data and VWAP deviation

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

        # Calculate average fill price (execution VWAP)
        avg_fill_price = weighted_price_sum / filled_quantity if filled_quantity > 0 else 0.0

        # Calculate VWAP deviation from benchmark
        vwap_deviation = None
        if benchmark_vwap is not None and benchmark_vwap > 0 and avg_fill_price > 0:
            vwap_deviation = (avg_fill_price - benchmark_vwap) / benchmark_vwap

        # Determine status
        from typing import Literal as L

        status: L["running", "completed", "cancelled", "failed"] = (
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
            benchmark_vwap=benchmark_vwap,
            vwap_deviation=vwap_deviation,
        )

    def recalculate_remaining_weights(
        self,
        original_weights: list[float],
        fills_per_slice: dict[int, float],
        current_slice_idx: int,
        total_quantity: float,
    ) -> list[float]:
        """Recalculate weights for remaining slices based on actual fills.

        Dynamically adjusts remaining execution when realized volume diverges
        from expected profile.

        Args:
            original_weights: Original volume weights for all slices (sum to 1.0)
            fills_per_slice: Actual fill quantities by slice index (absolute quantities)
            current_slice_idx: Current slice index (next slice to execute)
            total_quantity: Total quantity for the execution (to normalize fills)

        Returns:
            Adjusted weights for remaining slices (current_slice_idx onwards)

        Note:
            If actual cumulative fills deviate significantly from expected,
            redistributes remaining quantity across remaining slices using
            original volume profile weights.
        """
        # Calculate expected cumulative as fraction of total
        expected_cumulative = sum(original_weights[:current_slice_idx])

        # Calculate actual cumulative as fraction of total (normalize fills)
        actual_cumulative_qty = sum(fills_per_slice.values())
        actual_cumulative = actual_cumulative_qty / total_quantity if total_quantity > 0 else 0.0

        # If divergence is significant (>10%), rebalance remaining weights
        if expected_cumulative > 0:
            divergence = abs(actual_cumulative - expected_cumulative) / expected_cumulative
            if divergence > 0.1:  # 10% threshold
                # Recalculate remaining weights from original profile
                remaining_weights = original_weights[current_slice_idx:]
                if sum(remaining_weights) > 0:
                    # Normalize remaining weights to sum to 1.0
                    remaining_total = sum(remaining_weights)
                    return [w / remaining_total for w in remaining_weights]

        # No significant divergence, return original remaining weights
        remaining_weights = original_weights[current_slice_idx:]
        if sum(remaining_weights) > 0:
            remaining_total = sum(remaining_weights)
            return [w / remaining_total for w in remaining_weights]

        # Fallback: uniform distribution
        remaining_count = self.slice_count - current_slice_idx
        return [1.0 / remaining_count] * remaining_count if remaining_count > 0 else []

    async def replan_remaining_slices(
        self,
        original_intents: list[OrderIntent],
        fills: list[FillEvent],
        algo: ExecutionAlgorithm,
    ) -> list[OrderIntent]:
        """Dynamically adjust remaining slices based on actual fills.

        Implements the "Dynamically adjust if actual volume diverges" requirement
        by recalculating remaining slice quantities when fills deviate from expected.

        Args:
            original_intents: Original OrderIntent list from plan_execution
            fills: FillEvent list received so far
            algo: Original ExecutionAlgorithm configuration

        Returns:
            Adjusted OrderIntent list for remaining (unfilled) slices

        Note:
            This method should be called by orchestrator after each fill batch
            to detect divergence and replan remaining execution.
        """

        # Extract execution_id from first intent
        if not original_intents:
            return []

        execution_id = original_intents[0].meta["execution_id"]

        # Build fills_per_slice map
        fills_per_slice: dict[int, float] = {}
        for fill in fills:
            if fill.meta.get("execution_id") == execution_id:
                slice_idx = fill.meta.get("slice_idx")
                if slice_idx is not None:
                    fills_per_slice[slice_idx] = fills_per_slice.get(slice_idx, 0.0) + fill.qty

        # Find current slice index (first unfilled slice)
        current_slice_idx = 0
        for i in range(len(original_intents)):
            if i not in fills_per_slice:
                current_slice_idx = i
                break
        else:
            # All slices filled
            return []

        # Extract original weights from intents
        original_weights = [intent.meta["volume_weight"] for intent in original_intents]

        # Recalculate remaining weights
        adjusted_weights = self.recalculate_remaining_weights(
            original_weights=original_weights,
            fills_per_slice=fills_per_slice,
            current_slice_idx=current_slice_idx,
            total_quantity=algo.total_quantity,
        )

        # Calculate remaining quantity
        filled_quantity = sum(fills_per_slice.values())
        remaining_quantity = algo.total_quantity - filled_quantity

        # Get limit price and benchmark from original intents
        limit_price_base = original_intents[current_slice_idx].limit_price
        benchmark_vwap = original_intents[current_slice_idx].meta.get("benchmark_vwap")

        # Calculate remaining time and interval
        original_interval_ns = (
            original_intents[1].ts_local_ns - original_intents[0].ts_local_ns
            if len(original_intents) > 1
            else (algo.duration_seconds * 1_000_000_000) // self.slice_count
        )

        # Current time
        current_ts_ns = int(time.time() * 1e9)

        # Generate adjusted intents for remaining slices
        adjusted_intents: list[OrderIntent] = []
        for i, weight in enumerate(adjusted_weights):
            slice_idx = current_slice_idx + i
            slice_id = f"{execution_id}_slice_{slice_idx}"
            slice_qty = remaining_quantity * weight
            scheduled_ts_ns = current_ts_ns + (i * original_interval_ns)

            intent = OrderIntent(
                id=slice_id,
                ts_local_ns=scheduled_ts_ns,
                strategy_id=self.strategy_id,
                symbol=algo.symbol,
                side=algo.side,
                type=self.order_type,
                qty=slice_qty,
                limit_price=limit_price_base,
                meta={
                    "execution_id": execution_id,
                    "slice_id": slice_id,
                    "algo_type": "VWAP",
                    "slice_idx": slice_idx,
                    "volume_weight": weight,
                    "benchmark_vwap": benchmark_vwap,
                    "replanned": True,  # Mark as replanned
                },
            )
            adjusted_intents.append(intent)

        return adjusted_intents
