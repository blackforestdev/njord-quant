"""Tests for ExecutionPerformanceTracker (Phase 8.9)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from execution.contracts import ExecutionReport
from execution.performance import ExecutionPerformanceTracker
from research.data_reader import DataReader


@pytest.fixture
def temp_journal_dir() -> TemporaryDirectory[str]:
    """Create temporary journal directory for DataReader."""
    return TemporaryDirectory()


@pytest.fixture
def data_reader(temp_journal_dir: TemporaryDirectory[str]) -> DataReader:
    """Create DataReader with temporary journal directory."""
    return DataReader(temp_journal_dir.name)


@pytest.fixture
def tracker(data_reader: DataReader) -> ExecutionPerformanceTracker:
    """Create ExecutionPerformanceTracker fixture."""
    return ExecutionPerformanceTracker(data_reader)


def test_tracker_initializes_with_data_reader(data_reader: DataReader) -> None:
    """Test tracker initialization."""
    tracker = ExecutionPerformanceTracker(data_reader)
    assert tracker.data_reader is data_reader


def test_implementation_shortfall_zero_slippage(tracker: ExecutionPerformanceTracker) -> None:
    """Test implementation shortfall with zero slippage (perfect execution)."""
    # Perfect execution: fill price = arrival price
    report = ExecutionReport(
        execution_id="twap_test",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=10.0,
        remaining_quantity=0.0,
        avg_fill_price=50000.0,
        total_fees=5.0,
        slices_completed=4,
        slices_total=4,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
    )

    arrival_price = 50000.0
    shortfall = tracker.calculate_implementation_shortfall(report, arrival_price)

    # Zero slippage means zero total shortfall (price diff = 0)
    # Fees: 5 / (10 * 50000) * 10000 = 0.1 bps
    # But total shortfall measures price impact, not fees
    assert shortfall["total_shortfall_bps"] == pytest.approx(0.0, abs=0.01)
    assert shortfall["fees_bps"] == pytest.approx(0.1, abs=0.01)
    assert shortfall["market_impact_bps"] == pytest.approx(0.0, abs=0.01)
    assert shortfall["timing_cost_bps"] == pytest.approx(0.0, abs=0.01)


def test_implementation_shortfall_invalid_arrival(tracker: ExecutionPerformanceTracker) -> None:
    """Arrival price must be positive."""
    report = ExecutionReport(
        execution_id="twap_invalid",
        symbol="BTC/USDT",
        total_quantity=1.0,
        filled_quantity=1.0,
        remaining_quantity=0.0,
        avg_fill_price=100.0,
        total_fees=0.0,
        slices_completed=1,
        slices_total=1,
        status="completed",
        start_ts_ns=1,
        end_ts_ns=2,
        arrival_price=100.0,
    )

    with pytest.raises(ValueError, match="arrival_price must be > 0"):
        tracker.calculate_implementation_shortfall(report, 0.0)


def test_implementation_shortfall_with_slippage(tracker: ExecutionPerformanceTracker) -> None:
    """Test implementation shortfall with market impact and fees."""
    # Execution with slippage: fill price higher than arrival
    report = ExecutionReport(
        execution_id="vwap_test",
        symbol="BTC/USDT",
        total_quantity=100.0,
        filled_quantity=100.0,
        remaining_quantity=0.0,
        avg_fill_price=50100.0,  # 100 higher than arrival
        total_fees=50.0,
        slices_completed=10,
        slices_total=10,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
        benchmark_vwap=50050.0,
        vwap_deviation=0.001,  # 10 bps timing cost
    )

    arrival_price = 50000.0
    shortfall = tracker.calculate_implementation_shortfall(report, arrival_price)

    # Total slippage: (50100 - 50000) / 50000 * 10000 = 20 bps
    # Fees: 50 / (100 * 50100) * 10000 = 0.1 bps
    # Timing cost: 0.001 * 10000 = 10 bps (from vwap_deviation)
    # Market impact: 20 - 10 - 0.1 = 9.9 bps
    assert shortfall["total_shortfall_bps"] == pytest.approx(20.0, abs=0.1)
    assert shortfall["fees_bps"] == pytest.approx(0.1, abs=0.01)
    assert shortfall["timing_cost_bps"] == pytest.approx(10.0, abs=0.1)
    assert shortfall["market_impact_bps"] == pytest.approx(9.9, abs=0.1)


def test_implementation_shortfall_no_fills(tracker: ExecutionPerformanceTracker) -> None:
    """Test implementation shortfall with failed execution (no fills)."""
    # Failed execution: zero fills
    report = ExecutionReport(
        execution_id="twap_failed",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=0.0,
        remaining_quantity=10.0,
        avg_fill_price=0.0,
        total_fees=0.0,
        slices_completed=0,
        slices_total=4,
        status="failed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
    )

    arrival_price = 50000.0
    shortfall = tracker.calculate_implementation_shortfall(report, arrival_price)

    # No fills means zero shortfall
    assert shortfall["total_shortfall_bps"] == 0.0
    assert shortfall["market_impact_bps"] == 0.0
    assert shortfall["timing_cost_bps"] == 0.0
    assert shortfall["fees_bps"] == 0.0


def test_implementation_shortfall_without_vwap_benchmark(
    tracker: ExecutionPerformanceTracker,
) -> None:
    """Test implementation shortfall when VWAP benchmark unavailable."""
    # Execution without VWAP benchmark (50/50 split for timing/impact)
    report = ExecutionReport(
        execution_id="twap_test",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=10.0,
        remaining_quantity=0.0,
        avg_fill_price=50100.0,
        total_fees=5.0,
        slices_completed=4,
        slices_total=4,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
    )

    arrival_price = 50000.0
    shortfall = tracker.calculate_implementation_shortfall(report, arrival_price)

    # Total: 20 bps, Fees: 0.1 bps, Non-fee: 19.9 bps
    # 50/50 split: 9.95 bps each for market impact and timing
    assert shortfall["total_shortfall_bps"] == pytest.approx(20.0, abs=0.1)
    assert shortfall["fees_bps"] == pytest.approx(0.1, abs=0.01)
    assert shortfall["market_impact_bps"] == pytest.approx(9.95, abs=0.1)
    assert shortfall["timing_cost_bps"] == pytest.approx(9.95, abs=0.1)


def test_compare_to_arrival_benchmark(tracker: ExecutionPerformanceTracker) -> None:
    """Test benchmark comparison against arrival price."""
    report = ExecutionReport(
        execution_id="twap_test",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=10.0,
        remaining_quantity=0.0,
        avg_fill_price=50100.0,
        total_fees=5.0,
        slices_completed=4,
        slices_total=4,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
    )

    deviation = tracker.compare_to_benchmark(report, "arrival")

    # (50100 - 50000) / 50000 * 10000 = 20 bps
    assert deviation == pytest.approx(20.0, abs=0.1)


def test_compare_to_vwap_benchmark(tracker: ExecutionPerformanceTracker) -> None:
    """Test benchmark comparison against VWAP."""
    report = ExecutionReport(
        execution_id="vwap_test",
        symbol="BTC/USDT",
        total_quantity=100.0,
        filled_quantity=100.0,
        remaining_quantity=0.0,
        avg_fill_price=50100.0,
        total_fees=50.0,
        slices_completed=10,
        slices_total=10,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
        benchmark_vwap=50050.0,
    )

    deviation = tracker.compare_to_benchmark(report, "vwap")

    # (50100 - 50050) / 50050 * 10000 = ~10 bps
    assert deviation == pytest.approx(9.99, abs=0.1)


def test_compare_to_twap_benchmark(tracker: ExecutionPerformanceTracker) -> None:
    """Test benchmark comparison against TWAP (uses arrival as estimate)."""
    report = ExecutionReport(
        execution_id="twap_test",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=10.0,
        remaining_quantity=0.0,
        avg_fill_price=50050.0,
        total_fees=5.0,
        slices_completed=4,
        slices_total=4,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
    )

    deviation = tracker.compare_to_benchmark(report, "twap")

    # (50050 - 50000) / 50000 * 10000 = 10 bps
    assert deviation == pytest.approx(10.0, abs=0.1)


def test_compare_to_twap_missing_arrival_price(tracker: ExecutionPerformanceTracker) -> None:
    """TWAP benchmark requires arrival price."""
    report = ExecutionReport(
        execution_id="twap_missing",
        symbol="BTC/USDT",
        total_quantity=1.0,
        filled_quantity=1.0,
        remaining_quantity=0.0,
        avg_fill_price=100.0,
        total_fees=0.0,
        slices_completed=1,
        slices_total=1,
        status="completed",
        start_ts_ns=1,
        end_ts_ns=2,
    )

    with pytest.raises(ValueError, match="missing arrival_price"):
        tracker.compare_to_benchmark(report, "twap")


def test_compare_to_benchmark_no_fills(tracker: ExecutionPerformanceTracker) -> None:
    """Test benchmark comparison with no fills (edge case)."""
    report = ExecutionReport(
        execution_id="twap_failed",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=0.0,
        remaining_quantity=10.0,
        avg_fill_price=0.0,
        total_fees=0.0,
        slices_completed=0,
        slices_total=4,
        status="failed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        arrival_price=50000.0,
    )

    deviation = tracker.compare_to_benchmark(report, "arrival")

    # No fills means zero deviation
    assert deviation == 0.0


def test_compare_to_vwap_missing_benchmark(tracker: ExecutionPerformanceTracker) -> None:
    """Test benchmark comparison raises error when VWAP benchmark missing."""
    report = ExecutionReport(
        execution_id="twap_test",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=10.0,
        remaining_quantity=0.0,
        avg_fill_price=50100.0,
        total_fees=5.0,
        slices_completed=4,
        slices_total=4,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        # Missing benchmark_vwap
    )

    with pytest.raises(ValueError, match="missing benchmark_vwap"):
        tracker.compare_to_benchmark(report, "vwap")


def test_compare_to_arrival_missing_arrival_price(
    tracker: ExecutionPerformanceTracker,
) -> None:
    """Test benchmark comparison raises error when arrival price missing."""
    report = ExecutionReport(
        execution_id="twap_test",
        symbol="BTC/USDT",
        total_quantity=10.0,
        filled_quantity=10.0,
        remaining_quantity=0.0,
        avg_fill_price=50100.0,
        total_fees=5.0,
        slices_completed=4,
        slices_total=4,
        status="completed",
        start_ts_ns=1000000000,
        end_ts_ns=2000000000,
        # Missing arrival_price
    )

    with pytest.raises(ValueError, match="missing arrival_price"):
        tracker.compare_to_benchmark(report, "arrival")


def test_analyze_algorithm_performance_single_algo(
    tracker: ExecutionPerformanceTracker,
) -> None:
    """Test algorithm performance analysis with single algorithm."""
    reports = [
        ExecutionReport(
            execution_id="twap_001",
            symbol="BTC/USDT",
            total_quantity=10.0,
            filled_quantity=10.0,
            remaining_quantity=0.0,
            avg_fill_price=50000.0,
            total_fees=5.0,
            slices_completed=4,
            slices_total=4,
            status="completed",
            start_ts_ns=1000000000,
            end_ts_ns=2000000000,
            arrival_price=50000.0,
        ),
        ExecutionReport(
            execution_id="twap_002",
            symbol="ETH/USDT",
            total_quantity=20.0,
            filled_quantity=20.0,
            remaining_quantity=0.0,
            avg_fill_price=3000.0,
            total_fees=6.0,
            slices_completed=4,
            slices_total=4,
            status="completed",
            start_ts_ns=3000000000,
            end_ts_ns=4000000000,
            arrival_price=3000.0,
        ),
    ]

    df = tracker.analyze_algorithm_performance(reports)

    # Should have 1 row (TWAP algorithm)
    assert len(df) == 1
    assert df.iloc[0]["algorithm"] == "TWAP"
    assert df.iloc[0]["executions"] == 2
    assert df.iloc[0]["fill_rate"] == 100.0  # All filled
    assert df.iloc[0]["total_volume"] == 30.0  # 10 + 20


def test_analyze_algorithm_performance_multiple_algos(
    tracker: ExecutionPerformanceTracker,
) -> None:
    """Test algorithm performance analysis with multiple algorithms."""
    reports = [
        ExecutionReport(
            execution_id="twap_001",
            symbol="BTC/USDT",
            total_quantity=10.0,
            filled_quantity=10.0,
            remaining_quantity=0.0,
            avg_fill_price=50000.0,
            total_fees=5.0,
            slices_completed=4,
            slices_total=4,
            status="completed",
            start_ts_ns=1000000000,
            end_ts_ns=2000000000,
            arrival_price=50000.0,
        ),
        ExecutionReport(
            execution_id="vwap_001",
            symbol="ETH/USDT",
            total_quantity=20.0,
            filled_quantity=18.0,
            remaining_quantity=2.0,
            avg_fill_price=3000.0,
            total_fees=5.4,
            slices_completed=9,
            slices_total=10,
            status="running",
            start_ts_ns=3000000000,
            end_ts_ns=None,
            arrival_price=3000.0,
        ),
        ExecutionReport(
            execution_id="iceberg_001",
            symbol="BTC/USDT",
            total_quantity=50.0,
            filled_quantity=50.0,
            remaining_quantity=0.0,
            avg_fill_price=50100.0,
            total_fees=25.0,
            slices_completed=5,
            slices_total=5,
            status="completed",
            start_ts_ns=5000000000,
            end_ts_ns=6000000000,
            arrival_price=50000.0,
        ),
    ]

    df = tracker.analyze_algorithm_performance(reports)

    # Should have 3 rows (TWAP, VWAP, ICEBERG)
    assert len(df) == 3

    # Check TWAP metrics
    twap = df[df["algorithm"] == "TWAP"].iloc[0]
    assert twap["executions"] == 1
    assert twap["fill_rate"] == 100.0
    assert twap["total_volume"] == 10.0

    # Check VWAP metrics
    vwap = df[df["algorithm"] == "VWAP"].iloc[0]
    assert vwap["executions"] == 1
    assert vwap["fill_rate"] == 90.0  # 18 / 20
    assert vwap["total_volume"] == 18.0

    # Check Iceberg metrics
    iceberg = df[df["algorithm"] == "ICEBERG"].iloc[0]
    assert iceberg["executions"] == 1
    assert iceberg["fill_rate"] == 100.0
    assert iceberg["total_volume"] == 50.0
    # Slippage: (50100 - 50000) / 50000 * 10000 = 20 bps
    assert iceberg["avg_slippage_bps"] == pytest.approx(20.0, abs=0.1)


def test_analyze_algorithm_performance_empty_reports(
    tracker: ExecutionPerformanceTracker,
) -> None:
    """Test algorithm performance analysis with empty report list."""
    df = tracker.analyze_algorithm_performance([])

    # Should return empty DataFrame with correct columns
    assert len(df) == 0
    assert list(df.columns) == [
        "algorithm",
        "executions",
        "avg_fill_price",
        "avg_slippage_bps",
        "avg_fees_bps",
        "fill_rate",
        "total_volume",
    ]


def test_analyze_algorithm_performance_no_fills(
    tracker: ExecutionPerformanceTracker,
) -> None:
    """Test algorithm performance analysis with reports that have no fills."""
    reports = [
        ExecutionReport(
            execution_id="twap_failed",
            symbol="BTC/USDT",
            total_quantity=10.0,
            filled_quantity=0.0,
            remaining_quantity=10.0,
            avg_fill_price=0.0,
            total_fees=0.0,
            slices_completed=0,
            slices_total=4,
            status="failed",
            start_ts_ns=1000000000,
            end_ts_ns=2000000000,
        )
    ]

    df = tracker.analyze_algorithm_performance(reports)

    # Should return empty DataFrame (skip algorithms with no fills)
    assert len(df) == 0


def test_score_venue_quality_returns_metrics(
    tracker: ExecutionPerformanceTracker,
    temp_journal_dir: TemporaryDirectory[str],
) -> None:
    """Test venue quality scoring returns expected metrics."""
    # Prepare journal with fills for venue scoring
    pytest.importorskip("pandas")

    now_ns = time.time_ns()
    order1_ns = now_ns - 3_000_000_000
    order2_ns = now_ns - 2_000_000_000
    fills_path = Path(temp_journal_dir.name) / "fills.ndjson"
    fills_path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "order_id": "1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "qty": 5.0,
            "price": 101.0,
            "ts_fill_ns": order1_ns + 1_000_000_000,
            "meta": {
                "venue": "binanceus",
                "arrival_price": 100.0,
                "requested_qty": 6.0,
                "ts_order_ns": order1_ns,
            },
        },
        {
            "order_id": "2",
            "symbol": "BTC/USDT",
            "side": "buy",
            "qty": 3.0,
            "price": 100.5,
            "ts_fill_ns": order2_ns + 1_500_000_000,
            "meta": {
                "venue": "binanceus",
                "arrival_price": 100.0,
                "requested_qty": 4.0,
                "ts_order_ns": order2_ns,
            },
        },
        {
            "order_id": "3",
            "symbol": "BTC/USDT",
            "side": "buy",
            "qty": 2.0,
            "price": 99.0,
            "ts_fill_ns": order1_ns + 2_000_000_000,
            "meta": {
                "venue": "coinbase",
                "arrival_price": 99.5,
                "requested_qty": 2.0,
                "ts_order_ns": order1_ns,
            },
        },
    ]

    with fills_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")

    score = tracker.score_venue_quality("binanceus", "BTC/USDT", lookback_days=1)

    expected_slippage = ((101 - 100) / 100 * 10000 + (100.5 - 100) / 100 * 10000) / 2
    expected_fill_rate = ((5 + 3) / (6 + 4)) * 100
    expected_latency = ((1_000_000_000 / 1_000_000) + (1_500_000_000 / 1_000_000)) / 2

    assert score["avg_slippage_bps"] == pytest.approx(expected_slippage, abs=1e-6)
    assert score["fill_rate"] == pytest.approx(expected_fill_rate, abs=1e-6)
    assert score["avg_latency_ms"] == pytest.approx(expected_latency, abs=1e-6)

    other_score = tracker.score_venue_quality("coinbase", "BTC/USDT", lookback_days=1)
    assert other_score["avg_slippage_bps"] != score["avg_slippage_bps"]
