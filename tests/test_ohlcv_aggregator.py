from __future__ import annotations

from apps.ohlcv_aggregator.main import TradeAggregator


def test_aggregator_creation() -> None:
    """Test creating an aggregator."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    assert agg.symbol == "ATOM/USDT"
    assert agg.timeframe == "1m"
    assert agg.timeframe_ns == 60 * 1_000_000_000


def test_aggregator_single_trade() -> None:
    """Test aggregating a single trade."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # First trade in minute 0
    bar = agg.add_trade(price=10.0, qty=100.0, timestamp_ns=1000)

    # Should not emit bar yet (still in same minute)
    assert bar is None


def test_aggregator_complete_bar() -> None:
    """Test completing a bar when time window closes."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Trades in minute 0 (0-60 seconds)
    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0) is None
    assert agg.add_trade(price=10.5, qty=50.0, timestamp_ns=30_000_000_000) is None
    assert agg.add_trade(price=9.5, qty=75.0, timestamp_ns=50_000_000_000) is None
    assert agg.add_trade(price=10.2, qty=25.0, timestamp_ns=59_000_000_000) is None

    # Trade in minute 1 should close minute 0 bar
    bar = agg.add_trade(price=11.0, qty=10.0, timestamp_ns=60_000_000_000)

    assert bar is not None
    assert bar.symbol == "ATOM/USDT"
    assert bar.timeframe == "1m"
    assert bar.open == 10.0
    assert bar.high == 10.5
    assert bar.low == 9.5
    assert bar.close == 10.2
    assert bar.volume == 250.0


def test_aggregator_ohlc_logic() -> None:
    """Test OHLC calculation."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Add trades with specific prices
    assert agg.add_trade(price=10.0, qty=1.0, timestamp_ns=0) is None
    assert agg.add_trade(price=12.0, qty=1.0, timestamp_ns=10_000_000_000) is None
    assert agg.add_trade(price=8.0, qty=1.0, timestamp_ns=20_000_000_000) is None
    assert agg.add_trade(price=11.0, qty=1.0, timestamp_ns=30_000_000_000) is None

    # Close the bar
    bar = agg.add_trade(price=9.0, qty=1.0, timestamp_ns=60_000_000_000)

    assert bar is not None
    assert bar.open == 10.0  # First trade
    assert bar.high == 12.0  # Highest trade
    assert bar.low == 8.0  # Lowest trade
    assert bar.close == 11.0  # Last trade before close
    assert bar.volume == 4.0


def test_aggregator_multiple_bars() -> None:
    """Test creating multiple consecutive bars."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Bar 0
    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0) is None

    # Bar 1 (closes bar 0)
    bar0 = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)
    assert bar0 is not None
    assert bar0.close == 10.0

    # Bar 2 (closes bar 1)
    bar1 = agg.add_trade(price=12.0, qty=25.0, timestamp_ns=120_000_000_000)
    assert bar1 is not None
    assert bar1.close == 11.0


def test_aggregator_gap_handling() -> None:
    """Test gap handling with repeated close prices."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Create first bar
    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0) is None
    bar0 = agg.add_trade(price=10.5, qty=50.0, timestamp_ns=60_000_000_000)

    assert bar0 is not None
    assert bar0.close == 10.0

    # Check for gaps (simulate 3 minutes passing with no trades)
    current_time = 240_000_000_000  # 4 minutes
    gap_bars = agg.check_gap(current_time)

    # Should have 2 gap bars (minute 2 and minute 3)
    assert len(gap_bars) == 2

    # Gap bars should repeat the last close
    for gap_bar in gap_bars:
        assert gap_bar.open == 10.0
        assert gap_bar.high == 10.0
        assert gap_bar.low == 10.0
        assert gap_bar.close == 10.0
        assert gap_bar.volume == 0.0


def test_aggregator_5m_timeframe() -> None:
    """Test aggregator with 5m timeframe."""
    agg = TradeAggregator("ATOM/USDT", "5m")

    assert agg.timeframe_ns == 5 * 60 * 1_000_000_000

    # Trades within first 5 minutes
    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0) is None
    assert agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000) is None

    # Trade at 5 minutes should close the bar
    bar = agg.add_trade(price=12.0, qty=25.0, timestamp_ns=300_000_000_000)

    assert bar is not None
    assert bar.timeframe == "5m"
    assert bar.open == 10.0
    assert bar.close == 11.0


def test_aggregator_bar_alignment() -> None:
    """Test that bars align to timeframe boundaries."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Trade at arbitrary time
    timestamp = 12345_000_000_000  # Some arbitrary timestamp

    # Add trade
    assert agg.add_trade(price=10.0, qty=1.0, timestamp_ns=timestamp) is None

    # Bar start should be aligned to minute boundary
    assert agg.current_bar_start is not None
    assert agg.current_bar_start % (60 * 1_000_000_000) == 0


def test_aggregator_single_trade_bar() -> None:
    """Test edge case: bar with only one trade."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Single trade in first minute
    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0) is None

    # Next minute closes it
    bar = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)

    assert bar is not None
    assert bar.open == 10.0
    assert bar.high == 10.0
    assert bar.low == 10.0
    assert bar.close == 10.0
    assert bar.volume == 100.0


def test_aggregator_midnight_boundary() -> None:
    """Test handling of midnight boundary."""
    agg = TradeAggregator("ATOM/USDT", "1m")

    # Trade just before midnight (in nanoseconds)
    day_ns = 24 * 60 * 60 * 1_000_000_000
    before_midnight = day_ns - 1_000_000_000

    assert agg.add_trade(price=10.0, qty=100.0, timestamp_ns=before_midnight) is None

    # Trade after midnight
    after_midnight = day_ns + 1_000_000_000
    bar = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=after_midnight)

    assert bar is not None
    assert bar.close == 10.0
