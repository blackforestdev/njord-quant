"""Execution simulator for backtesting.

This module provides execution simulation for backtesting, integrating
execution algorithms with slippage models to produce realistic fill events.

The simulator uses a synchronous interface compatible with backtest engines
and wraps async executors using SyncExecutionWrapper.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal, cast

import pandas as pd

from core.contracts import FillEvent, OrderIntent
from execution.adapters import SyncExecutionWrapper
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm, ExecutionReport
from execution.slippage import SlippageModel

if TYPE_CHECKING:
    from research.data_reader import DataReader


class ExecutionSimulator:
    """Simulate execution algorithms in backtesting.

    This class bridges async executors with sync backtest engines,
    applying slippage models to generate realistic fill events.

    Attributes:
        slippage_model: Slippage model for fill simulation
        data_reader: Data reader for market data (unused in current implementation)
    """

    def __init__(
        self,
        slippage_model: SlippageModel,
        data_reader: DataReader | None = None,
    ) -> None:
        """Initialize execution simulator.

        Args:
            slippage_model: Slippage model to apply to fills
            data_reader: Optional data reader for market data lookups
        """
        self.slippage_model = slippage_model
        self.data_reader = data_reader

    def simulate_execution(
        self,
        executor: BaseExecutor,
        algo: ExecutionAlgorithm,
        market_data: pd.DataFrame,
    ) -> ExecutionReport:
        """Simulate execution algorithm in backtest (synchronous).

        Args:
            executor: Execution algorithm executor (TWAP, VWAP, etc.)
            algo: Execution algorithm configuration
            market_data: OHLCV bars for simulation period
                Required columns: ts_open, open, high, low, close, volume

        Returns:
            Execution report with fill statistics

        Raises:
            ValueError: If market_data is empty or missing required columns

        Note:
            This is a synchronous interface for backtest compatibility.
            Uses SyncExecutionWrapper internally to call async executors.
        """
        if market_data.empty:
            raise ValueError("market_data cannot be empty")

        required_cols = {"ts_open", "open", "high", "low", "close", "volume"}
        missing_cols = required_cols - set(market_data.columns)
        if missing_cols:
            raise ValueError(f"market_data missing required columns: {missing_cols}")

        # Plan execution via executor
        fills = self._plan_and_execute(executor, algo, market_data)

        # Build execution report
        return self._build_execution_report(algo, fills)

    def _plan_and_execute(
        self,
        executor: BaseExecutor,
        algo: ExecutionAlgorithm,
        market_data: pd.DataFrame,
    ) -> list[FillEvent]:
        """Plan execution via executor, simulate fills.

        Args:
            executor: Execution algorithm executor
            algo: Execution algorithm configuration
            market_data: OHLCV bars for simulation period

        Returns:
            List of simulated fill events
        """
        # Use SyncExecutionWrapper to call async executor
        wrapper = SyncExecutionWrapper(executor)
        intents = wrapper.plan_execution_sync(algo)

        # Simulate fills for each OrderIntent
        fills: list[FillEvent] = []
        for intent in intents:
            # Extract scheduled time from intent metadata
            scheduled_ts_ns = intent.meta.get("scheduled_ts_ns", market_data.iloc[0]["ts_open"])

            # Find market bar closest to scheduled time
            market_bar = self._find_market_bar(market_data, scheduled_ts_ns)

            # Apply slippage and create fill
            fill = self._apply_slippage(
                intent=intent,
                market_price=market_bar["close"],
                market_volume=market_bar["volume"],
                scheduled_ts_ns=scheduled_ts_ns,
            )
            fills.append(fill)

        return fills

    def _find_market_bar(
        self,
        market_data: pd.DataFrame,
        scheduled_ts_ns: int,
    ) -> pd.Series:
        """Find market bar closest to scheduled time.

        Args:
            market_data: OHLCV bars
            scheduled_ts_ns: Scheduled execution time (nanoseconds)

        Returns:
            Market bar (pandas Series)
        """
        # Find bar that contains or is closest to scheduled time
        # Use ts_open for bar selection
        idx = (market_data["ts_open"] - scheduled_ts_ns).abs().idxmin()
        # DataFrame.loc with scalar index returns Series (use cast for type safety)
        return cast("pd.Series[Any]", market_data.loc[idx])

    def _apply_slippage(
        self,
        intent: OrderIntent,
        market_price: float,
        market_volume: float,
        scheduled_ts_ns: int,
    ) -> FillEvent:
        """Apply slippage model to OrderIntent execution.

        Args:
            intent: Order intent to execute
            market_price: Reference price from market data
            market_volume: Market volume for slippage calculation
            scheduled_ts_ns: Scheduled execution time (nanoseconds)

        Returns:
            FillEvent with slippage applied
        """
        # Estimate bid-ask spread (use simple heuristic: 0.05% of price)
        # In production, this would come from market data
        bid_ask_spread = market_price * 0.0005

        # Calculate slippage in price units
        slippage = self.slippage_model.calculate_slippage(
            order_size=intent.qty,
            market_volume=market_volume,
            bid_ask_spread=bid_ask_spread,
            reference_price=market_price,
        )

        # Adjust fill price based on side (buy: pay more, sell: receive less)
        fill_price = market_price + slippage if intent.side == "buy" else market_price - slippage

        # Calculate fee (simple: 0.1% of notional)
        notional = intent.qty * fill_price
        fee = notional * 0.001

        # Create fill event
        return FillEvent(
            order_id=intent.id,
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
            price=fill_price,
            ts_fill_ns=scheduled_ts_ns,
            fee=fee,
            meta=intent.meta.copy(),
        )

    def _build_execution_report(
        self,
        algo: ExecutionAlgorithm,
        fills: list[FillEvent],
    ) -> ExecutionReport:
        """Build execution report from fills.

        Args:
            algo: Execution algorithm configuration
            fills: List of fill events

        Returns:
            ExecutionReport with execution statistics
        """
        if not fills:
            # No fills - return empty report
            execution_id = str(uuid.uuid4())
            return ExecutionReport(
                execution_id=execution_id,
                symbol=algo.symbol,
                total_quantity=algo.total_quantity,
                filled_quantity=0.0,
                remaining_quantity=algo.total_quantity,
                avg_fill_price=0.0,
                total_fees=0.0,
                slices_completed=0,
                slices_total=len(fills),
                status="failed",
                start_ts_ns=0,
                end_ts_ns=None,
            )

        # Extract execution_id from first fill
        execution_id = fills[0].meta.get("execution_id", str(uuid.uuid4()))

        # Calculate statistics
        filled_quantity = sum(fill.qty for fill in fills)
        total_cost = sum(fill.qty * fill.price for fill in fills)
        avg_fill_price = total_cost / filled_quantity if filled_quantity > 0 else 0.0
        total_fees = sum(fill.fee for fill in fills)
        remaining_quantity = max(0.0, algo.total_quantity - filled_quantity)

        # Determine status
        status: Literal["running", "completed", "cancelled", "failed"]
        if filled_quantity >= algo.total_quantity:
            status = "completed"
        elif filled_quantity > 0:
            status = "running"
        else:
            status = "failed"

        # Time range
        start_ts_ns = min(fill.ts_fill_ns for fill in fills)
        end_ts_ns = max(fill.ts_fill_ns for fill in fills) if status == "completed" else None

        return ExecutionReport(
            execution_id=execution_id,
            symbol=algo.symbol,
            total_quantity=algo.total_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            avg_fill_price=avg_fill_price,
            total_fees=total_fees,
            slices_completed=len(fills),
            slices_total=len(fills),
            status=status,
            start_ts_ns=start_ts_ns,
            end_ts_ns=end_ts_ns,
        )
