"""Execution layer contracts.

This module defines contracts for execution algorithms, slices, and reports.
All contracts are immutable and include proper validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ExecutionAlgorithm:
    """Configuration for execution algorithm.

    Attributes:
        algo_type: Type of execution algorithm (TWAP, VWAP, Iceberg, POV)
        symbol: Trading pair symbol
        side: Order side (buy or sell)
        total_quantity: Total quantity to execute
        duration_seconds: Execution duration in seconds
        params: Algorithm-specific parameters

    Raises:
        ValueError: If total_quantity <= 0 or duration_seconds <= 0
    """

    algo_type: Literal["TWAP", "VWAP", "Iceberg", "POV"]
    symbol: str
    side: Literal["buy", "sell"]
    total_quantity: float
    duration_seconds: int
    params: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate execution algorithm configuration."""
        if self.total_quantity <= 0:
            raise ValueError(f"total_quantity must be > 0, got {self.total_quantity}")
        if self.duration_seconds <= 0:
            raise ValueError(f"duration_seconds must be > 0, got {self.duration_seconds}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of ExecutionAlgorithm
        """
        return {
            "algo_type": self.algo_type,
            "symbol": self.symbol,
            "side": self.side,
            "total_quantity": self.total_quantity,
            "duration_seconds": self.duration_seconds,
            "params": self.params.copy(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionAlgorithm:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with algorithm configuration

        Returns:
            ExecutionAlgorithm instance
        """
        return cls(
            algo_type=data["algo_type"],
            symbol=data["symbol"],
            side=data["side"],
            total_quantity=data["total_quantity"],
            duration_seconds=data["duration_seconds"],
            params=data.get("params", {}),
        )


@dataclass(frozen=True)
class ExecutionSlice:
    """Individual slice of parent execution order.

    Attributes:
        execution_id: Parent execution ID
        slice_id: Unique slice identifier
        symbol: Trading pair symbol
        side: Order side (buy or sell)
        quantity: Slice quantity
        limit_price: Limit price for order (None for market orders)
        scheduled_ts_ns: Scheduled execution time (nanoseconds)
        status: Slice status
        client_order_id: Client order ID (maps to OrderIntent.id)

    Raises:
        ValueError: If quantity <= 0 or status not in allowed set
    """

    execution_id: str
    slice_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    limit_price: float | None
    scheduled_ts_ns: int
    status: Literal["pending", "submitted", "filled", "cancelled"]
    client_order_id: str

    def __post_init__(self) -> None:
        """Validate execution slice configuration."""
        if self.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {self.quantity}")
        allowed_statuses = {"pending", "submitted", "filled", "cancelled"}
        if self.status not in allowed_statuses:
            raise ValueError(f"status must be one of {allowed_statuses}, got {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of ExecutionSlice
        """
        return {
            "execution_id": self.execution_id,
            "slice_id": self.slice_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "scheduled_ts_ns": self.scheduled_ts_ns,
            "status": self.status,
            "client_order_id": self.client_order_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionSlice:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with slice data

        Returns:
            ExecutionSlice instance
        """
        return cls(
            execution_id=data["execution_id"],
            slice_id=data["slice_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            limit_price=data.get("limit_price"),
            scheduled_ts_ns=data["scheduled_ts_ns"],
            status=data["status"],
            client_order_id=data["client_order_id"],
        )


@dataclass(frozen=True)
class ExecutionReport:
    """Progress report for execution algorithm.

    Attributes:
        execution_id: Execution ID
        symbol: Trading pair symbol
        total_quantity: Total quantity to execute
        filled_quantity: Quantity filled so far
        remaining_quantity: Remaining quantity
        avg_fill_price: Average fill price
        total_fees: Total fees paid
        slices_completed: Number of slices completed
        slices_total: Total number of slices
        status: Execution status
        start_ts_ns: Execution start time (nanoseconds)
        end_ts_ns: Execution end time (nanoseconds, None if not finished)
    """

    execution_id: str
    symbol: str
    total_quantity: float
    filled_quantity: float
    remaining_quantity: float
    avg_fill_price: float
    total_fees: float
    slices_completed: int
    slices_total: int
    status: Literal["running", "completed", "cancelled", "failed"]
    start_ts_ns: int
    end_ts_ns: int | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of ExecutionReport
        """
        return {
            "execution_id": self.execution_id,
            "symbol": self.symbol,
            "total_quantity": self.total_quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "avg_fill_price": self.avg_fill_price,
            "total_fees": self.total_fees,
            "slices_completed": self.slices_completed,
            "slices_total": self.slices_total,
            "status": self.status,
            "start_ts_ns": self.start_ts_ns,
            "end_ts_ns": self.end_ts_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionReport:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with report data

        Returns:
            ExecutionReport instance
        """
        return cls(
            execution_id=data["execution_id"],
            symbol=data["symbol"],
            total_quantity=data["total_quantity"],
            filled_quantity=data["filled_quantity"],
            remaining_quantity=data["remaining_quantity"],
            avg_fill_price=data["avg_fill_price"],
            total_fees=data["total_fees"],
            slices_completed=data["slices_completed"],
            slices_total=data["slices_total"],
            status=data["status"],
            start_ts_ns=data["start_ts_ns"],
            end_ts_ns=data.get("end_ts_ns"),
        )
