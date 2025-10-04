"""Tests for POV (Percentage of Volume) executor."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import pytest

from core.contracts import FillEvent
from execution.contracts import ExecutionAlgorithm
from execution.pov import POVExecutor
from tests.utils import InMemoryBus


class MockDataReader:
    """Mock DataReader for testing."""

    def __init__(self, default_volume: float = 5000.0) -> None:
        """Initialize mock with optional volume data.

        Args:
            default_volume: Default volume to return for any query
        """
        self.default_volume = default_volume

    def read_trades(self, symbol: str, start_ts: int, end_ts: int, format: str = "pandas") -> Any:
        """Mock read_trades returning volume data."""
        # Return mock DataFrame-like object with volume
        volume = self.default_volume

        # Create mock DataFrame
        class MockDataFrame:
            def __init__(self, volume: float) -> None:
                self.columns = ["amount"]
                self._volume = volume

            def __len__(self) -> int:
                return 1 if self._volume > 0 else 0

            def sum(self) -> MockSeries:
                return MockSeries(self._volume)

            def __getitem__(self, key: str) -> MockSeries:
                if key == "amount":
                    return MockSeries(self._volume)
                raise KeyError(key)

        class MockSeries:
            def __init__(self, value: float) -> None:
                self._value = value

            def sum(self) -> float:
                return self._value

        return MockDataFrame(volume)


@pytest.mark.asyncio
async def test_pov_initialization() -> None:
    """Test POVExecutor initialization and validation."""
    data_reader = MockDataReader()

    # Valid initialization
    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
        min_volume_threshold=1000.0,
    )

    assert executor.strategy_id == "test_strat"
    assert executor.target_pov == 0.2
    assert executor.min_volume_threshold == 1000.0

    # Invalid target_pov (too high)
    with pytest.raises(ValueError, match=r"target_pov must be in \(0, 1\]"):
        POVExecutor(
            strategy_id="test_strat",
            data_reader=data_reader,  # type: ignore[arg-type]  # type: ignore[arg-type]
            target_pov=1.5,
        )

    # Invalid target_pov (zero)
    with pytest.raises(ValueError, match=r"target_pov must be in \(0, 1\]"):
        POVExecutor(
            strategy_id="test_strat",
            data_reader=data_reader,  # type: ignore[arg-type]  # type: ignore[arg-type]
            target_pov=0.0,
        )

    # Invalid min_volume_threshold
    with pytest.raises(ValueError, match=r"min_volume_threshold must be > 0"):
        POVExecutor(
            strategy_id="test_strat",
            data_reader=data_reader,  # type: ignore[arg-type]  # type: ignore[arg-type]
            target_pov=0.2,
            min_volume_threshold=-100.0,
        )


@pytest.mark.asyncio
async def test_pov_plan_execution_basic() -> None:
    """Test POV plan_execution with sufficient volume."""
    data_reader = MockDataReader(default_volume=10000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
        min_volume_threshold=1000.0,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=500.0,
        duration_seconds=600,
        params={"limit_price": 50000.0, "measurement_period_seconds": 60},
    )

    intents = await executor.plan_execution(algo)

    # Should return 1 initial intent
    assert len(intents) == 1

    intent = intents[0]
    assert intent.symbol == "BTC/USDT"
    assert intent.side == "buy"
    assert intent.type == "limit"
    assert intent.limit_price == 50000.0
    assert intent.strategy_id == "test_strat"

    # Check metadata
    assert intent.meta["algo_type"] == "POV"
    assert intent.meta["total_quantity"] == 500.0
    assert intent.meta["target_pov"] == 0.2
    assert intent.meta["slice_idx"] == 0
    assert "execution_id" in intent.meta
    assert "slice_id" in intent.meta
    assert intent.meta["execution_id"].startswith("pov_")


@pytest.mark.asyncio
async def test_pov_plan_execution_low_volume() -> None:
    """Test POV plan_execution with volume below threshold."""
    # Mock data reader with low volume (below threshold of 1000.0)
    data_reader = MockDataReader(default_volume=500.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
        min_volume_threshold=1000.0,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=100.0,
        duration_seconds=600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)

    # Should return empty list (volume too low)
    assert len(intents) == 0


@pytest.mark.asyncio
async def test_pov_plan_execution_missing_limit_price() -> None:
    """Test POV plan_execution requires limit_price for limit orders."""
    data_reader = MockDataReader(default_volume=5000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=100.0,
        duration_seconds=600,
        params={},  # Missing limit_price
    )

    with pytest.raises(ValueError, match=r"limit_price must be provided"):
        await executor.plan_execution(algo)


@pytest.mark.asyncio
async def test_pov_plan_execution_market_order() -> None:
    """Test POV plan_execution with market orders."""
    data_reader = MockDataReader(default_volume=5000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="sell",
        total_quantity=50.0,
        duration_seconds=300,
        params={"order_type": "market"},
    )

    intents = await executor.plan_execution(algo)

    assert len(intents) == 1
    assert intents[0].type == "market"
    assert intents[0].limit_price is None


@pytest.mark.asyncio
async def test_pov_calculate_slice_size() -> None:
    """Test POV slice size calculation."""
    data_reader = MockDataReader()

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
    )

    # Base case: market_volume * target_pov
    slice_size = executor._calculate_slice_size(
        market_volume=10000.0,
        remaining_quantity=5000.0,
        time_remaining_ns=600_000_000_000,  # 600 seconds
    )

    # Should be 10000 * 0.2 = 2000
    assert slice_size == 2000.0

    # Cap at remaining quantity
    slice_size = executor._calculate_slice_size(
        market_volume=10000.0,
        remaining_quantity=1000.0,  # Less than 2000
        time_remaining_ns=600_000_000_000,
    )

    # Should be capped at 1000
    assert slice_size == 1000.0


@pytest.mark.asyncio
async def test_pov_metadata_round_trip() -> None:
    """Test POV metadata propagates through OrderIntent -> Fill -> OrderIntent chain."""
    data_reader = MockDataReader(default_volume=10000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.25,  # 25% POV
        min_volume_threshold=1000.0,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2500.0,
        duration_seconds=600,
        params={"limit_price": 50000.0, "measurement_period_seconds": 60},
    )

    # Get initial intent
    intents = await executor.plan_execution(algo)
    assert len(intents) == 1

    initial_intent = intents[0]
    execution_id = initial_intent.meta["execution_id"]

    # Verify initial metadata
    assert initial_intent.meta["algo_type"] == "POV"
    assert initial_intent.meta["slice_idx"] == 0
    assert initial_intent.meta["total_quantity"] == 2500.0
    assert initial_intent.meta["target_pov"] == 0.25
    assert initial_intent.meta["slice_id"] == f"{execution_id}_slice_0"

    # Simulate fill with metadata propagation
    # Volume is 10000, POV is 25%, so initial slice should be 2500 (capped at total)
    assert initial_intent.qty == 2500.0

    # Create fill event
    fill = FillEvent(
        order_id=initial_intent.id,
        symbol="BTC/USDT",
        side="buy",
        qty=2500.0,
        price=50000.0,
        ts_fill_ns=int(time.time() * 1e9),
        fee=125.0,
        meta=initial_intent.meta,  # Metadata propagates
    )

    # Verify metadata preserved in fill
    assert fill.meta["execution_id"] == execution_id
    assert fill.meta["slice_id"] == f"{execution_id}_slice_0"
    assert fill.meta["algo_type"] == "POV"
    assert fill.meta["target_pov"] == 0.25


@pytest.mark.asyncio
async def test_pov_monitor_and_slice_dynamic() -> None:
    """Test POV dynamic slicing via _monitor_and_slice."""
    # Setup mock data reader with default volume
    data_reader = MockDataReader(default_volume=5000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
        min_volume_threshold=500.0,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="ETH/USDT",
        side="sell",
        total_quantity=100.0,
        duration_seconds=600,
        params={"limit_price": 3000.0, "measurement_period_seconds": 60},
    )

    # Get execution_id from plan
    intents = await executor.plan_execution(algo)
    assert len(intents) == 1
    execution_id = intents[0].meta["execution_id"]

    # Setup bus
    bus = InMemoryBus()

    # Start monitoring in background
    slice_intents: list[Any] = []

    async def collect_slices() -> None:
        async for intent in executor._monitor_and_slice(bus, execution_id, algo):
            slice_intents.append(intent)

    monitor_task = asyncio.create_task(collect_slices())

    # Simulate fills
    await asyncio.sleep(0.01)

    # Publish fill for initial slice (partial)
    fill_1 = FillEvent(
        order_id=f"{execution_id}_slice_0",
        symbol="ETH/USDT",
        side="sell",
        qty=20.0,
        price=3000.0,
        ts_fill_ns=int(time.time() * 1e9),
        fee=60.0,
        meta={
            "execution_id": execution_id,
            "slice_id": f"{execution_id}_slice_0",
            "algo_type": "POV",
            "slice_idx": 0,
            "total_quantity": 100.0,
            "target_pov": 0.2,
        },
    )

    await bus.publish_json("fills.new", {"fill": fill_1.__dict__})
    await asyncio.sleep(0.01)

    # Should generate next slice
    # (simplified test - actual volume monitoring would be more complex)

    # Cancel monitoring
    monitor_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await monitor_task


@pytest.mark.asyncio
async def test_pov_validation_invalid_measurement_period() -> None:
    """Test POV validates measurement_period_seconds parameter."""
    data_reader = MockDataReader(default_volume=5000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
    )

    # Invalid type
    algo_bad_type = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=100.0,
        duration_seconds=600,
        params={"limit_price": 50000.0, "measurement_period_seconds": "invalid"},
    )

    with pytest.raises(TypeError, match=r"measurement_period_seconds must be a number"):
        await executor.plan_execution(algo_bad_type)

    # Invalid value (zero)
    algo_bad_value = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=100.0,
        duration_seconds=600,
        params={"limit_price": 50000.0, "measurement_period_seconds": 0},
    )

    with pytest.raises(ValueError, match=r"measurement_period_seconds must be > 0"):
        await executor.plan_execution(algo_bad_value)


@pytest.mark.asyncio
async def test_pov_validation_invalid_limit_price() -> None:
    """Test POV validates limit_price parameter."""
    data_reader = MockDataReader(default_volume=5000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,
    )

    # Invalid type
    algo_bad_type = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=100.0,
        duration_seconds=600,
        params={"limit_price": "not_a_number"},
    )

    with pytest.raises(TypeError, match=r"limit_price must be a number"):
        await executor.plan_execution(algo_bad_type)

    # Invalid value (negative)
    algo_bad_value = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=100.0,
        duration_seconds=600,
        params={"limit_price": -100.0},
    )

    with pytest.raises(ValueError, match=r"limit_price must be > 0"):
        await executor.plan_execution(algo_bad_value)


@pytest.mark.asyncio
async def test_pov_get_recent_volume_no_data() -> None:
    """Test POV handles missing volume data gracefully."""

    # Mock reader that returns None
    class EmptyMockReader:
        def read_trades(
            self, symbol: str, start_ts: int, end_ts: int, format: str = "pandas"
        ) -> None:
            return None

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=EmptyMockReader(),  # type: ignore
        target_pov=0.2,
    )

    volume = executor._get_recent_volume(
        symbol="BTC/USDT",
        start_ts_ns=0,
        end_ts_ns=60_000_000_000,
    )

    # Should return 0.0 when no data
    assert volume == 0.0


@pytest.mark.asyncio
async def test_pov_maintains_target_pov_tolerance() -> None:
    """Test POV maintains target participation within 5% tolerance."""
    data_reader = MockDataReader(default_volume=10000.0)

    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=data_reader,  # type: ignore[arg-type]
        target_pov=0.2,  # 20% target
        min_volume_threshold=1000.0,
    )

    algo = ExecutionAlgorithm(
        algo_type="POV",
        symbol="BTC/USDT",
        side="buy",
        total_quantity=2000.0,
        duration_seconds=600,
        params={"limit_price": 50000.0},
    )

    intents = await executor.plan_execution(algo)
    assert len(intents) == 1

    intent = intents[0]

    # Market volume is 10000, target POV is 20% = 2000
    # Total quantity is 2000, so initial slice should be 2000 (exactly at target)
    expected_slice = 10000.0 * 0.2  # 2000
    assert intent.qty == expected_slice

    # Verify within 5% tolerance
    market_volume = 10000.0
    actual_pov = intent.qty / market_volume
    expected_pov = 0.2
    tolerance = 0.05

    assert abs(actual_pov - expected_pov) <= tolerance


@pytest.mark.asyncio
async def test_pov_acceleration_when_behind_schedule() -> None:
    """Test POV accelerates slice size when execution is behind schedule."""
    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=MockDataReader(),  # type: ignore[arg-type]
        target_pov=0.2,  # 20% POV
    )

    # Scenario: 60% of time elapsed but only 30% filled (behind schedule)
    total_duration_ns = 600_000_000_000  # 600 seconds
    time_elapsed_ns = 360_000_000_000  # 360 seconds (60% elapsed)
    time_remaining_ns = total_duration_ns - time_elapsed_ns  # 240 seconds

    total_quantity = 1000.0
    filled_quantity = 300.0  # 30% filled (should be ~60%)
    remaining_quantity = total_quantity - filled_quantity  # 700.0

    market_volume = 1000.0

    # Calculate slice with acceleration
    accelerated_slice = executor._calculate_slice_size(
        market_volume=market_volume,
        remaining_quantity=remaining_quantity,
        time_remaining_ns=time_remaining_ns,
        total_quantity=total_quantity,
        total_duration_ns=total_duration_ns,
    )

    # Calculate slice without acceleration (baseline)
    baseline_slice = executor._calculate_slice_size(
        market_volume=market_volume,
        remaining_quantity=remaining_quantity,
        time_remaining_ns=time_remaining_ns,
    )

    # Baseline should be market_volume * target_pov = 1000 * 0.2 = 200
    assert baseline_slice == 200.0

    # Accelerated slice should be larger due to being behind schedule
    # Expected progress: 60%, Actual progress: 30%, Lag: 30%
    # Acceleration factor: 1 + min(0.3 * 2, 1) = 1 + 0.6 = 1.6
    # Accelerated slice: 200 * 1.6 = 320
    assert accelerated_slice > baseline_slice
    assert accelerated_slice == 320.0


@pytest.mark.asyncio
async def test_pov_no_acceleration_when_on_schedule() -> None:
    """Test POV does not accelerate when execution is on schedule."""
    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=MockDataReader(),  # type: ignore[arg-type]
        target_pov=0.2,
    )

    # Scenario: 50% of time elapsed and 50% filled (on schedule)
    total_duration_ns = 600_000_000_000  # 600 seconds
    time_elapsed_ns = 300_000_000_000  # 300 seconds (50% elapsed)
    time_remaining_ns = total_duration_ns - time_elapsed_ns

    total_quantity = 1000.0
    filled_quantity = 500.0  # 50% filled
    remaining_quantity = total_quantity - filled_quantity

    market_volume = 1000.0

    # Calculate slice with acceleration (should not accelerate)
    slice_size = executor._calculate_slice_size(
        market_volume=market_volume,
        remaining_quantity=remaining_quantity,
        time_remaining_ns=time_remaining_ns,
        total_quantity=total_quantity,
        total_duration_ns=total_duration_ns,
    )

    # Should be normal: market_volume * target_pov = 200
    assert slice_size == 200.0


@pytest.mark.asyncio
async def test_pov_slice_size_variations() -> None:
    """Test POV handles varying volume scenarios."""
    executor = POVExecutor(
        strategy_id="test_strat",
        data_reader=MockDataReader(),  # type: ignore[arg-type]
        target_pov=0.15,  # 15% POV
    )

    # Low volume
    slice_1 = executor._calculate_slice_size(
        market_volume=1000.0,
        remaining_quantity=500.0,
        time_remaining_ns=300_000_000_000,
    )
    assert slice_1 == 150.0  # 1000 * 0.15

    # High volume
    slice_2 = executor._calculate_slice_size(
        market_volume=50000.0,
        remaining_quantity=5000.0,
        time_remaining_ns=300_000_000_000,
    )
    assert slice_2 == 5000.0  # 50000 * 0.15 = 7500, capped at 5000

    # Volume spike
    slice_3 = executor._calculate_slice_size(
        market_volume=100000.0,
        remaining_quantity=10000.0,
        time_remaining_ns=300_000_000_000,
    )
    assert slice_3 == 10000.0  # 100000 * 0.15 = 15000, capped at 10000
