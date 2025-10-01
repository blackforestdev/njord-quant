from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from core.contracts import OHLCVBar


def test_ohlcv_bar_creation() -> None:
    """Test creating an OHLCVBar."""
    bar = OHLCVBar(
        symbol="ATOM/USDT",
        timeframe="1m",
        ts_open=1000000000,
        ts_close=1060000000,
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.2,
        volume=1000.0,
    )

    assert bar.symbol == "ATOM/USDT"
    assert bar.timeframe == "1m"
    assert bar.ts_open == 1000000000
    assert bar.ts_close == 1060000000
    assert bar.open == 10.0
    assert bar.high == 10.5
    assert bar.low == 9.5
    assert bar.close == 10.2
    assert bar.volume == 1000.0


def test_ohlcv_bar_immutable() -> None:
    """Test that OHLCVBar is immutable (frozen)."""
    bar = OHLCVBar(
        symbol="ATOM/USDT",
        timeframe="1m",
        ts_open=1000000000,
        ts_close=1060000000,
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.2,
        volume=1000.0,
    )

    with pytest.raises(FrozenInstanceError):
        bar.symbol = "BTC/USDT"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        bar.close = 11.0  # type: ignore[misc]


def test_ohlcv_bar_serializable() -> None:
    """Test that OHLCVBar is serializable to dict."""
    bar = OHLCVBar(
        symbol="ATOM/USDT",
        timeframe="5m",
        ts_open=1000000000,
        ts_close=1300000000,
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.2,
        volume=1500.0,
    )

    bar_dict = asdict(bar)

    assert bar_dict == {
        "symbol": "ATOM/USDT",
        "timeframe": "5m",
        "ts_open": 1000000000,
        "ts_close": 1300000000,
        "open": 10.0,
        "high": 10.5,
        "low": 9.5,
        "close": 10.2,
        "volume": 1500.0,
    }


def test_ohlcv_bar_from_dict() -> None:
    """Test creating OHLCVBar from dict."""
    bar_dict: dict[str, str | int | float] = {
        "symbol": "ATOM/USDT",
        "timeframe": "1h",
        "ts_open": 1000000000,
        "ts_close": 3600000000000,
        "open": 10.0,
        "high": 10.5,
        "low": 9.5,
        "close": 10.2,
        "volume": 5000.0,
    }

    bar = OHLCVBar(
        symbol=str(bar_dict["symbol"]),
        timeframe=str(bar_dict["timeframe"]),
        ts_open=int(bar_dict["ts_open"]),
        ts_close=int(bar_dict["ts_close"]),
        open=float(bar_dict["open"]),
        high=float(bar_dict["high"]),
        low=float(bar_dict["low"]),
        close=float(bar_dict["close"]),
        volume=float(bar_dict["volume"]),
    )

    assert bar.symbol == "ATOM/USDT"
    assert bar.timeframe == "1h"
    assert bar.ts_open == 1000000000
    assert bar.ts_close == 3600000000000
    assert bar.open == 10.0
    assert bar.high == 10.5
    assert bar.low == 9.5
    assert bar.close == 10.2
    assert bar.volume == 5000.0


def test_ohlcv_bar_typed_correctly() -> None:
    """Test that OHLCVBar has correct types."""
    bar = OHLCVBar(
        symbol="ATOM/USDT",
        timeframe="1m",
        ts_open=1000000000,
        ts_close=1060000000,
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.2,
        volume=1000.0,
    )

    assert isinstance(bar.symbol, str)
    assert isinstance(bar.timeframe, str)
    assert isinstance(bar.ts_open, int)
    assert isinstance(bar.ts_close, int)
    assert isinstance(bar.open, float)
    assert isinstance(bar.high, float)
    assert isinstance(bar.low, float)
    assert isinstance(bar.close, float)
    assert isinstance(bar.volume, float)


def test_ohlcv_bar_different_timeframes() -> None:
    """Test creating bars with different timeframes."""
    timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

    for tf in timeframes:
        bar = OHLCVBar(
            symbol="ATOM/USDT",
            timeframe=tf,
            ts_open=1000000000,
            ts_close=1060000000,
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.2,
            volume=1000.0,
        )
        assert bar.timeframe == tf


def test_ohlcv_bar_roundtrip() -> None:
    """Test serialization roundtrip (dict -> bar -> dict)."""
    original = OHLCVBar(
        symbol="ATOM/USDT",
        timeframe="1m",
        ts_open=1000000000,
        ts_close=1060000000,
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.2,
        volume=1000.0,
    )

    # Serialize to dict
    bar_dict = asdict(original)

    # Deserialize from dict
    restored = OHLCVBar(**bar_dict)

    # Should be equal
    assert restored == original
    assert asdict(restored) == bar_dict
