from __future__ import annotations

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.replay_engine.main import ReplayEngine, parse_speed, parse_timestamp
from core.contracts import OHLCVBar


@pytest.fixture
def mock_bus() -> MagicMock:
    """Create a mock bus."""
    bus = MagicMock()
    bus.publish_json = AsyncMock()
    return bus


@pytest.fixture
def sample_journal_dir() -> Generator[Path, None, None]:
    """Create a temporary journal directory with sample data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create sample journal file
        journal_file = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=10.0 + i,
                high=11.0 + i,
                low=9.0 + i,
                close=10.5 + i,
                volume=100.0,
            )
            for i in range(10)
        ]

        with open(journal_file, "w") as f:
            for bar in bars:
                f.write(json.dumps(bar.__dict__) + "\n")

        yield journal_dir


def test_replay_engine_creation(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test creating a replay engine."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=1.0)

    assert engine.journal_dir == sample_journal_dir
    assert engine.bus == mock_bus
    assert engine.speed_multiplier == 1.0


@pytest.mark.asyncio
async def test_replay_basic(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test basic replay functionality."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    # Replay all bars (max speed, no delay)
    count = await engine.replay("ATOM/USDT", "1m", start_ns=0, end_ns=2**63 - 1)

    assert count == 10
    assert mock_bus.publish_json.call_count == 10

    # Verify first published bar
    first_call = mock_bus.publish_json.call_args_list[0]
    topic, bar_dict = first_call[0]

    assert topic == "md.ohlcv.1m.ATOM/USDT"
    assert bar_dict["symbol"] == "ATOM/USDT"
    assert bar_dict["timeframe"] == "1m"
    assert bar_dict["close"] == 10.5


@pytest.mark.asyncio
async def test_replay_time_range(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test replay with time range filtering."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    # Replay bars 3-6
    start_ns = 3 * 60_000_000_000
    end_ns = 7 * 60_000_000_000

    count = await engine.replay("ATOM/USDT", "1m", start_ns=start_ns, end_ns=end_ns)

    assert count == 4
    assert mock_bus.publish_json.call_count == 4


@pytest.mark.asyncio
async def test_replay_speed_control(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test replay speed control with timing."""
    # Use 100x speed for faster test
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=100.0)

    import time

    start_time = time.time()

    # Replay first 3 bars (2 delays between them)
    # At 100x speed: 60 seconds between bars = 0.6 seconds real time
    # Total: ~1.2 seconds
    await engine.replay("ATOM/USDT", "1m", start_ns=0, end_ns=3 * 60_000_000_000)

    elapsed = time.time() - start_time

    # Should take approximately 1.2 seconds (with some tolerance)
    assert 1.0 < elapsed < 2.0


@pytest.mark.asyncio
async def test_replay_max_speed(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test max speed replay (no delays)."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    import time

    start_time = time.time()

    # Replay all bars at max speed (should be very fast)
    await engine.replay("ATOM/USDT", "1m", start_ns=0, end_ns=2**63 - 1)

    elapsed = time.time() - start_time

    # Should take less than 1 second (no delays)
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_replay_deterministic(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test that replay is deterministic across runs."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    # First replay
    await engine.replay("ATOM/USDT", "1m", start_ns=0, end_ns=2**63 - 1)
    first_calls = [call[0][1] for call in mock_bus.publish_json.call_args_list]

    # Reset mock
    mock_bus.publish_json.reset_mock()

    # Second replay
    await engine.replay("ATOM/USDT", "1m", start_ns=0, end_ns=2**63 - 1)
    second_calls = [call[0][1] for call in mock_bus.publish_json.call_args_list]

    # Should be identical
    assert first_calls == second_calls


@pytest.mark.asyncio
async def test_replay_multiple_symbols(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test concurrent replay of multiple symbols."""
    # Create second symbol's journal
    journal_file = sample_journal_dir / "ohlcv.1m.BTCUSDT.ndjson"

    bars = [
        OHLCVBar(
            symbol="BTC/USDT",
            timeframe="1m",
            ts_open=i * 60_000_000_000,
            ts_close=(i + 1) * 60_000_000_000,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=10.0,
        )
        for i in range(10)
    ]

    with open(journal_file, "w") as f:
        for bar in bars:
            f.write(json.dumps(bar.__dict__) + "\n")

    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    # Replay both symbols concurrently
    results = await engine.replay_multiple(
        symbols=["ATOM/USDT", "BTC/USDT"],
        timeframe="1m",
        start_ns=0,
        end_ns=2**63 - 1,
    )

    assert results["ATOM/USDT"] == 10
    assert results["BTC/USDT"] == 10
    assert mock_bus.publish_json.call_count == 20


@pytest.mark.asyncio
async def test_replay_multiple_no_interference(
    sample_journal_dir: Path, mock_bus: MagicMock
) -> None:
    """Test that concurrent replays don't interfere with each other."""
    # Create second symbol with different bar count
    journal_file = sample_journal_dir / "ohlcv.1m.BTCUSDT.ndjson"

    bars = [
        OHLCVBar(
            symbol="BTC/USDT",
            timeframe="1m",
            ts_open=i * 60_000_000_000,
            ts_close=(i + 1) * 60_000_000_000,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=10.0,
        )
        for i in range(5)  # Only 5 bars
    ]

    with open(journal_file, "w") as f:
        for bar in bars:
            f.write(json.dumps(bar.__dict__) + "\n")

    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    results = await engine.replay_multiple(
        symbols=["ATOM/USDT", "BTC/USDT"],
        timeframe="1m",
        start_ns=0,
        end_ns=2**63 - 1,
    )

    # Each symbol should have correct count
    assert results["ATOM/USDT"] == 10
    assert results["BTC/USDT"] == 5

    # Verify topics are correct
    atom_calls = [call for call in mock_bus.publish_json.call_args_list if "ATOM" in call[0][0]]
    btc_calls = [call for call in mock_bus.publish_json.call_args_list if "BTC" in call[0][0]]

    assert len(atom_calls) == 10
    assert len(btc_calls) == 5


def test_parse_timestamp() -> None:
    """Test timestamp parsing."""
    # Test UTC timestamp
    ts_ns = parse_timestamp("2025-09-01T00:00:00Z")
    assert ts_ns == 1756684800_000_000_000

    # Test with timezone offset
    ts_ns = parse_timestamp("2025-09-01T00:00:00+00:00")
    assert ts_ns == 1756684800_000_000_000


def test_parse_speed() -> None:
    """Test speed string parsing."""
    assert parse_speed("1x") == 1.0
    assert parse_speed("10x") == 10.0
    assert parse_speed("100x") == 100.0
    assert parse_speed("max") == 0.0

    # Test without 'x' suffix
    assert parse_speed("5") == 5.0

    # Test case insensitivity
    assert parse_speed("MAX") == 0.0
    assert parse_speed("10X") == 10.0


@pytest.mark.asyncio
async def test_replay_empty_range(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test replay with empty time range."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    # Time range with no bars
    count = await engine.replay(
        "ATOM/USDT", "1m", start_ns=1000 * 60_000_000_000, end_ns=2000 * 60_000_000_000
    )

    assert count == 0
    assert mock_bus.publish_json.call_count == 0


@pytest.mark.asyncio
async def test_replay_event_sequence(sample_journal_dir: Path, mock_bus: MagicMock) -> None:
    """Test that replay produces correct event sequence."""
    engine = ReplayEngine(sample_journal_dir, mock_bus, speed_multiplier=0.0)

    await engine.replay("ATOM/USDT", "1m", start_ns=0, end_ns=2**63 - 1)

    # Verify events are in chronological order
    for i in range(10):
        call = mock_bus.publish_json.call_args_list[i]
        _topic, bar_dict = call[0]

        assert bar_dict["ts_open"] == i * 60_000_000_000
        assert bar_dict["close"] == 10.5 + i
