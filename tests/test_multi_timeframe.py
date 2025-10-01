from __future__ import annotations

from apps.ohlcv_aggregator.main import MultiTimeframeAggregator


def test_multi_timeframe_creation() -> None:
    """Test creating a multi-timeframe aggregator."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m", "1h"])

    assert agg.symbol == "ATOM/USDT"
    assert agg.timeframes == ["1m", "5m", "1h"]
    assert len(agg.aggregators) == 3


def test_multi_timeframe_single_bar() -> None:
    """Test that only 1m completes initially."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m"])

    # Trade in minute 0
    bars = agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0)
    assert len(bars) == 0

    # Trade in minute 1 should close 1m bar only
    bars = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)

    assert "1m" in bars
    assert "5m" not in bars
    assert bars["1m"].close == 10.0


def test_multi_timeframe_alignment() -> None:
    """Test that bars align to wall-clock boundaries."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m", "1h"])

    # Arbitrary starting time
    start_time = 12345_000_000_000

    # Add first trade
    agg.add_trade(price=10.0, qty=1.0, timestamp_ns=start_time)

    # Check all aggregators have aligned bar starts
    for _tf, aggregator in agg.aggregators.items():
        assert aggregator.current_bar_start is not None
        # Bar start should be aligned to timeframe boundary
        assert aggregator.current_bar_start % aggregator.timeframe_ns == 0


def test_multi_timeframe_concurrent_aggregation() -> None:
    """Test concurrent aggregation of multiple timeframes."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m", "15m"])

    # Simulate 16 minutes of trades (one per minute)
    for minute in range(16):
        timestamp_ns = minute * 60_000_000_000
        price = 10.0 + minute * 0.1

        bars = agg.add_trade(price=price, qty=100.0, timestamp_ns=timestamp_ns)

        # Check which bars completed
        if minute >= 1:
            # 1m bar should complete every minute (after first)
            assert "1m" in bars
        if minute == 5:
            # 5m bar should complete at minute 5
            assert "5m" in bars
        if minute == 15:
            # 15m bar should complete at minute 15
            assert "15m" in bars


def test_multi_timeframe_no_drift() -> None:
    """Test that there's no drift across 24h simulation."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m", "1h"])

    # Simulate 24 hours of trades (one per minute)
    minute_ns = 60 * 1_000_000_000

    minute_bars_count = 0
    five_minute_bars_count = 0
    hour_bars_count = 0

    for minute in range(24 * 60 + 1):  # 24 hours + 1 to close last bars
        timestamp_ns = minute * minute_ns
        bars = agg.add_trade(price=10.0, qty=1.0, timestamp_ns=timestamp_ns)

        if "1m" in bars:
            minute_bars_count += 1
        if "5m" in bars:
            five_minute_bars_count += 1
        if "1h" in bars:
            hour_bars_count += 1

    # Verify expected bar counts
    assert minute_bars_count == 24 * 60  # 1440 minutes
    assert five_minute_bars_count == 24 * 12  # 288 five-minute bars
    assert hour_bars_count == 24  # 24 hours


def test_multi_timeframe_higher_derived_from_1m() -> None:
    """Test that higher timeframes can be derived from 1m bars."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m"])

    # Create 5 one-minute bars
    for minute in range(6):
        timestamp_ns = minute * 60_000_000_000
        price = 10.0 + minute
        bars = agg.add_trade(price=price, qty=100.0, timestamp_ns=timestamp_ns)

        if "1m" in bars:
            # Store minute bars
            pass

    # After 5 minutes, we should have 1m bars stored
    assert len(agg.minute_bars) == 5


def test_multi_timeframe_single_timeframe() -> None:
    """Test multi-timeframe aggregator with single timeframe."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m"])

    # Should work like regular aggregator
    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0) == {}

    bars = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)
    assert len(bars) == 1
    assert "1m" in bars


def test_multi_timeframe_wall_clock_alignment() -> None:
    """Test that bars align to wall-clock boundaries (e.g., 1h at :00)."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1h"])

    # Start at some arbitrary time
    hour_ns = 60 * 60 * 1_000_000_000
    start_time = 7 * hour_ns + 30 * 60 * 1_000_000_000  # 7:30

    # Add first trade
    agg.add_trade(price=10.0, qty=1.0, timestamp_ns=start_time)

    # Bar should be aligned to hour boundary (7:00, not 7:30)
    aggregator_1h = agg.aggregators["1h"]
    assert aggregator_1h.current_bar_start == 7 * hour_ns


def test_multi_timeframe_empty_timeframes() -> None:
    """Test edge case: empty timeframes list."""
    agg = MultiTimeframeAggregator("ATOM/USDT", [])

    bars = agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0)

    # Should return empty dict
    assert bars == {}


def test_multi_timeframe_all_standard_timeframes() -> None:
    """Test with all standard timeframes."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m", "15m", "1h", "4h", "1d"])

    assert len(agg.aggregators) == 6

    # Add a trade
    bars = agg.add_trade(price=10.0, qty=1.0, timestamp_ns=0)

    # No bars should complete on first trade
    assert len(bars) == 0
