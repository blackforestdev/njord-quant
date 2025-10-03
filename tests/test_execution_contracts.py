"""Tests for execution contracts (Phase 8.1)."""

import time

import pytest

from execution.contracts import ExecutionAlgorithm, ExecutionReport, ExecutionSlice


def test_execution_algorithm_valid() -> None:
    """Verify ExecutionAlgorithm creation with valid parameters."""
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={"slice_count": 10},
    )

    assert algo.algo_type == "TWAP"
    assert algo.symbol == "BTC/USDT"
    assert algo.side == "buy"
    assert algo.total_quantity == 1.0
    assert algo.duration_seconds == 300
    assert algo.params == {"slice_count": 10}


def test_execution_algorithm_validation_quantity() -> None:
    """Verify ExecutionAlgorithm rejects invalid total_quantity."""
    with pytest.raises(ValueError, match="total_quantity must be > 0"):
        ExecutionAlgorithm(
            algo_type="TWAP",
            symbol="BTC/USDT",
            side="buy",
            total_quantity=0.0,
            duration_seconds=300,
            params={},
        )

    with pytest.raises(ValueError, match="total_quantity must be > 0"):
        ExecutionAlgorithm(
            algo_type="TWAP",
            symbol="BTC/USDT",
            side="buy",
            total_quantity=-1.0,
            duration_seconds=300,
            params={},
        )


def test_execution_algorithm_validation_duration() -> None:
    """Verify ExecutionAlgorithm rejects invalid duration_seconds."""
    with pytest.raises(ValueError, match="duration_seconds must be > 0"):
        ExecutionAlgorithm(
            algo_type="TWAP",
            symbol="BTC/USDT",
            side="buy",
            total_quantity=1.0,
            duration_seconds=0,
            params={},
        )

    with pytest.raises(ValueError, match="duration_seconds must be > 0"):
        ExecutionAlgorithm(
            algo_type="TWAP",
            symbol="BTC/USDT",
            side="buy",
            total_quantity=1.0,
            duration_seconds=-300,
            params={},
        )


def test_execution_algorithm_immutable() -> None:
    """Verify ExecutionAlgorithm is immutable (frozen)."""
    algo = ExecutionAlgorithm(
        algo_type="TWAP",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=1.0,
        duration_seconds=300,
        params={},
    )

    with pytest.raises((AttributeError, TypeError)):
        algo.total_quantity = 2.0  # type: ignore[misc]


def test_execution_algorithm_serialization() -> None:
    """Verify ExecutionAlgorithm to_dict/from_dict round-trip."""
    algo = ExecutionAlgorithm(
        algo_type="VWAP",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=5.0,
        duration_seconds=600,
        params={"max_participation": 0.2},
    )

    # Serialize
    data = algo.to_dict()
    assert data["algo_type"] == "VWAP"
    assert data["symbol"] == "ETH/USDT"
    assert data["side"] == "sell"
    assert data["total_quantity"] == 5.0
    assert data["duration_seconds"] == 600
    assert data["params"] == {"max_participation": 0.2}

    # Deserialize
    restored = ExecutionAlgorithm.from_dict(data)
    assert restored == algo


def test_execution_slice_valid() -> None:
    """Verify ExecutionSlice creation with valid parameters."""
    ts = int(time.time() * 1e9)
    slice_ = ExecutionSlice(
        execution_id="exec_123",
        slice_id="slice_0",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        limit_price=50000.0,
        scheduled_ts_ns=ts,
        status="pending",
        client_order_id="intent_abc",
    )

    assert slice_.execution_id == "exec_123"
    assert slice_.slice_id == "slice_0"
    assert slice_.symbol == "BTC/USDT"
    assert slice_.side == "buy"
    assert slice_.quantity == 0.1
    assert slice_.limit_price == 50000.0
    assert slice_.scheduled_ts_ns == ts
    assert slice_.status == "pending"
    assert slice_.client_order_id == "intent_abc"


def test_execution_slice_validation_quantity() -> None:
    """Verify ExecutionSlice rejects invalid quantity."""
    ts = int(time.time() * 1e9)

    with pytest.raises(ValueError, match="quantity must be > 0"):
        ExecutionSlice(
            execution_id="exec_123",
            slice_id="slice_0",
            symbol="BTC/USDT",
            side="buy",
            quantity=0.0,
            limit_price=50000.0,
            scheduled_ts_ns=ts,
            status="pending",
            client_order_id="intent_abc",
        )

    with pytest.raises(ValueError, match="quantity must be > 0"):
        ExecutionSlice(
            execution_id="exec_123",
            slice_id="slice_0",
            symbol="BTC/USDT",
            side="buy",
            quantity=-0.5,
            limit_price=50000.0,
            scheduled_ts_ns=ts,
            status="pending",
            client_order_id="intent_abc",
        )


def test_execution_slice_validation_status() -> None:
    """Verify ExecutionSlice rejects invalid status."""
    ts = int(time.time() * 1e9)

    with pytest.raises(ValueError, match="status must be one of"):
        ExecutionSlice(
            execution_id="exec_123",
            slice_id="slice_0",
            symbol="BTC/USDT",
            side="buy",
            quantity=0.1,
            limit_price=50000.0,
            scheduled_ts_ns=ts,
            status="invalid_status",  # type: ignore[arg-type]
            client_order_id="intent_abc",
        )


def test_execution_slice_timestamp_suffix() -> None:
    """Verify ExecutionSlice uses *_ns suffix for timestamp."""
    ts = int(time.time() * 1e9)
    slice_ = ExecutionSlice(
        execution_id="exec_123",
        slice_id="slice_0",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        limit_price=None,  # Market order
        scheduled_ts_ns=ts,
        status="pending",
        client_order_id="intent_abc",
    )

    # Verify timestamp field name ends with _ns
    assert hasattr(slice_, "scheduled_ts_ns")
    assert isinstance(slice_.scheduled_ts_ns, int)


def test_execution_slice_client_order_id() -> None:
    """Verify ExecutionSlice includes client_order_id for fill tracking."""
    slice_ = ExecutionSlice(
        execution_id="exec_123",
        slice_id="slice_0",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        limit_price=50000.0,
        scheduled_ts_ns=int(time.time() * 1e9),
        status="pending",
        client_order_id="intent_abc",
    )

    # client_order_id should map to OrderIntent.id
    assert slice_.client_order_id == "intent_abc"


def test_execution_slice_immutable() -> None:
    """Verify ExecutionSlice is immutable (frozen)."""
    slice_ = ExecutionSlice(
        execution_id="exec_123",
        slice_id="slice_0",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.1,
        limit_price=50000.0,
        scheduled_ts_ns=int(time.time() * 1e9),
        status="pending",
        client_order_id="intent_abc",
    )

    with pytest.raises((AttributeError, TypeError)):
        slice_.status = "filled"  # type: ignore[misc]


def test_execution_slice_serialization() -> None:
    """Verify ExecutionSlice to_dict/from_dict round-trip."""
    ts = int(time.time() * 1e9)
    slice_ = ExecutionSlice(
        execution_id="exec_456",
        slice_id="slice_1",
        symbol="ETH/USDT",
        side="sell",
        quantity=0.5,
        limit_price=3000.0,
        scheduled_ts_ns=ts,
        status="submitted",
        client_order_id="intent_xyz",
    )

    # Serialize
    data = slice_.to_dict()
    assert data["execution_id"] == "exec_456"
    assert data["slice_id"] == "slice_1"
    assert data["symbol"] == "ETH/USDT"
    assert data["side"] == "sell"
    assert data["quantity"] == 0.5
    assert data["limit_price"] == 3000.0
    assert data["scheduled_ts_ns"] == ts
    assert data["status"] == "submitted"
    assert data["client_order_id"] == "intent_xyz"

    # Deserialize
    restored = ExecutionSlice.from_dict(data)
    assert restored == slice_


def test_execution_report_valid() -> None:
    """Verify ExecutionReport creation with valid parameters."""
    start_ts = int(time.time() * 1e9)
    end_ts = start_ts + 300_000_000_000  # 5 minutes later

    report = ExecutionReport(
        execution_id="exec_123",
        symbol="BTC/USDT",
        total_quantity=1.0,
        filled_quantity=0.6,
        remaining_quantity=0.4,
        avg_fill_price=50100.0,
        total_fees=15.03,
        slices_completed=6,
        slices_total=10,
        status="running",
        start_ts_ns=start_ts,
        end_ts_ns=end_ts,
    )

    assert report.execution_id == "exec_123"
    assert report.symbol == "BTC/USDT"
    assert report.total_quantity == 1.0
    assert report.filled_quantity == 0.6
    assert report.remaining_quantity == 0.4
    assert report.avg_fill_price == 50100.0
    assert report.total_fees == 15.03
    assert report.slices_completed == 6
    assert report.slices_total == 10
    assert report.status == "running"
    assert report.start_ts_ns == start_ts
    assert report.end_ts_ns == end_ts


def test_execution_report_timestamp_suffix() -> None:
    """Verify ExecutionReport uses *_ns suffix for timestamps."""
    start_ts = int(time.time() * 1e9)

    report = ExecutionReport(
        execution_id="exec_123",
        symbol="BTC/USDT",
        total_quantity=1.0,
        filled_quantity=0.0,
        remaining_quantity=1.0,
        avg_fill_price=0.0,
        total_fees=0.0,
        slices_completed=0,
        slices_total=10,
        status="running",
        start_ts_ns=start_ts,
        end_ts_ns=None,  # Not finished yet
    )

    # Verify timestamp field names end with _ns
    assert hasattr(report, "start_ts_ns")
    assert hasattr(report, "end_ts_ns")
    assert isinstance(report.start_ts_ns, int)
    assert report.end_ts_ns is None  # Can be None for running executions


def test_execution_report_immutable() -> None:
    """Verify ExecutionReport is immutable (frozen)."""
    report = ExecutionReport(
        execution_id="exec_123",
        symbol="BTC/USDT",
        total_quantity=1.0,
        filled_quantity=0.0,
        remaining_quantity=1.0,
        avg_fill_price=0.0,
        total_fees=0.0,
        slices_completed=0,
        slices_total=10,
        status="running",
        start_ts_ns=int(time.time() * 1e9),
        end_ts_ns=None,
    )

    with pytest.raises((AttributeError, TypeError)):
        report.status = "completed"  # type: ignore[misc]


def test_execution_report_serialization() -> None:
    """Verify ExecutionReport to_dict/from_dict round-trip."""
    start_ts = int(time.time() * 1e9)
    end_ts = start_ts + 600_000_000_000  # 10 minutes later

    report = ExecutionReport(
        execution_id="exec_789",
        symbol="ETH/USDT",
        total_quantity=5.0,
        filled_quantity=5.0,
        remaining_quantity=0.0,
        avg_fill_price=2950.5,
        total_fees=44.26,
        slices_completed=20,
        slices_total=20,
        status="completed",
        start_ts_ns=start_ts,
        end_ts_ns=end_ts,
    )

    # Serialize
    data = report.to_dict()
    assert data["execution_id"] == "exec_789"
    assert data["symbol"] == "ETH/USDT"
    assert data["total_quantity"] == 5.0
    assert data["filled_quantity"] == 5.0
    assert data["remaining_quantity"] == 0.0
    assert data["avg_fill_price"] == 2950.5
    assert data["total_fees"] == 44.26
    assert data["slices_completed"] == 20
    assert data["slices_total"] == 20
    assert data["status"] == "completed"
    assert data["start_ts_ns"] == start_ts
    assert data["end_ts_ns"] == end_ts

    # Deserialize
    restored = ExecutionReport.from_dict(data)
    assert restored == report


def test_execution_report_with_none_end_timestamp() -> None:
    """Verify ExecutionReport handles None end_ts_ns correctly."""
    report = ExecutionReport(
        execution_id="exec_running",
        symbol="BTC/USDT",
        total_quantity=1.0,
        filled_quantity=0.5,
        remaining_quantity=0.5,
        avg_fill_price=50000.0,
        total_fees=7.5,
        slices_completed=5,
        slices_total=10,
        status="running",
        start_ts_ns=int(time.time() * 1e9),
        end_ts_ns=None,
    )

    # Serialize
    data = report.to_dict()
    assert data["end_ts_ns"] is None

    # Deserialize
    restored = ExecutionReport.from_dict(data)
    assert restored.end_ts_ns is None
    assert restored == report
