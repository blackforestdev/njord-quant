"""VWAP (Volume-Weighted Average Price) execution algorithm.

This module implements VWAP execution strategy that weights order slices
based on historical volume patterns.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Literal

from core.contracts import OrderIntent
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm

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

        # Calculate volume profile
        volume_weights = self._calculate_volume_profile(
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
            )
            intents.append(intent)

        return intents

    def _calculate_volume_profile(self, symbol: str, duration_seconds: int) -> list[float]:
        """Calculate expected volume distribution from historical data.

        Args:
            symbol: Trading pair symbol
            duration_seconds: Execution duration in seconds

        Returns:
            List of volume weights summing to 1.0

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
                return [1.0 / self.slice_count] * self.slice_count

            # Extract volume column
            volumes = df["volume"].values

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
                return [1.0 / self.slice_count] * self.slice_count

            # Normalize to weights summing to 1.0
            weights = [vol / total_volume for vol in slice_volumes]

            return weights

        except Exception:
            # Fall back to uniform distribution on any error
            # Production version would log the error
            return [1.0 / self.slice_count] * self.slice_count

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
