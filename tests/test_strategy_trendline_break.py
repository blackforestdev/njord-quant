from __future__ import annotations

import json
from pathlib import Path

from strategies.samples.trendline_break import TrendlineBreak


def test_trendline_break_golden() -> None:
    """Test TrendlineBreak strategy against golden data."""
    golden_path = Path("tests/golden/trendline_break.jsonl")

    strategy = TrendlineBreak()
    strategy.configure(
        {
            "lookback_periods": 20,
            "breakout_threshold": 0.02,
            "qty": 1.0,
            "symbol": "ATOM/USDT",
        }
    )

    expectations: list[dict[str, str]] = []
    actual_signals: list[dict[str, str]] = []

    with open(golden_path) as f:
        for line in f:
            entry = json.loads(line)

            if entry["type"] == "event":
                # Process event
                intents = list(strategy.on_event(entry))

                if intents:
                    # Record signal
                    intent = intents[0]
                    actual_signals.append(
                        {
                            "side": intent.side,
                            "symbol": intent.symbol,
                            "qty": str(intent.qty),
                        }
                    )

            elif entry["type"] == "expect":
                # Record expectation
                expectations.append({"side": entry["side"], "reason": entry["reason"]})

    # Verify we got expected number of signals
    assert len(actual_signals) == len(
        expectations
    ), f"Expected {len(expectations)} signals, got {len(actual_signals)}"

    # Verify signal sides match
    for i, (actual, expected) in enumerate(zip(actual_signals, expectations, strict=True)):
        assert actual["side"] == expected["side"], (
            f"Signal {i}: expected {expected['side']}, got {actual['side']} "
            f"(reason: {expected['reason']})"
        )


def test_trendline_break_basic() -> None:
    """Test basic TrendlineBreak functionality."""
    strategy = TrendlineBreak()
    strategy.configure(
        {
            "lookback_periods": 5,
            "breakout_threshold": 0.02,
            "qty": 1.0,
            "symbol": "ATOM/USDT",
        }
    )

    # Feed uptrend prices
    events = [
        {"symbol": "ATOM/USDT", "price": 10.0, "ts_local_ns": 1000},
        {"symbol": "ATOM/USDT", "price": 10.1, "ts_local_ns": 2000},
        {"symbol": "ATOM/USDT", "price": 10.2, "ts_local_ns": 3000},
        {"symbol": "ATOM/USDT", "price": 10.3, "ts_local_ns": 4000},
        {"symbol": "ATOM/USDT", "price": 10.4, "ts_local_ns": 5000},
    ]

    for event in events:
        list(strategy.on_event(event))

    # Feed breakout price (should trigger buy)
    # Trendline projects to 10.5, so 10.72 is > 2% breakout
    breakout_event = {"symbol": "ATOM/USDT", "price": 10.72, "ts_local_ns": 6000}
    intents = list(strategy.on_event(breakout_event))

    assert len(intents) == 1
    assert intents[0].side == "buy"
    assert intents[0].symbol == "ATOM/USDT"
    assert intents[0].qty == 1.0


def test_trendline_break_downtrend() -> None:
    """Test TrendlineBreak detects downward breakout."""
    strategy = TrendlineBreak()
    strategy.configure(
        {
            "lookback_periods": 5,
            "breakout_threshold": 0.02,
            "qty": 1.0,
            "symbol": "ATOM/USDT",
        }
    )

    # Feed downtrend prices
    events = [
        {"symbol": "ATOM/USDT", "price": 10.4, "ts_local_ns": 1000},
        {"symbol": "ATOM/USDT", "price": 10.3, "ts_local_ns": 2000},
        {"symbol": "ATOM/USDT", "price": 10.2, "ts_local_ns": 3000},
        {"symbol": "ATOM/USDT", "price": 10.1, "ts_local_ns": 4000},
        {"symbol": "ATOM/USDT", "price": 10.0, "ts_local_ns": 5000},
    ]

    for event in events:
        list(strategy.on_event(event))

    # Feed breakout price (should trigger sell)
    # Trendline projects to 9.9, so 9.68 is > 2% below
    breakout_event = {"symbol": "ATOM/USDT", "price": 9.68, "ts_local_ns": 6000}
    intents = list(strategy.on_event(breakout_event))

    assert len(intents) == 1
    assert intents[0].side == "sell"


def test_trendline_break_no_signal_on_small_move() -> None:
    """Test that small moves don't trigger signals."""
    strategy = TrendlineBreak()
    strategy.configure(
        {
            "lookback_periods": 5,
            "breakout_threshold": 0.05,  # Higher threshold
            "qty": 1.0,
            "symbol": "ATOM/USDT",
        }
    )

    # Feed prices
    events = [
        {"symbol": "ATOM/USDT", "price": 10.0, "ts_local_ns": 1000},
        {"symbol": "ATOM/USDT", "price": 10.1, "ts_local_ns": 2000},
        {"symbol": "ATOM/USDT", "price": 10.2, "ts_local_ns": 3000},
        {"symbol": "ATOM/USDT", "price": 10.3, "ts_local_ns": 4000},
        {"symbol": "ATOM/USDT", "price": 10.4, "ts_local_ns": 5000},
    ]

    for event in events:
        list(strategy.on_event(event))

    # Feed small move (should not trigger)
    small_move_event = {"symbol": "ATOM/USDT", "price": 10.5, "ts_local_ns": 6000}
    intents = list(strategy.on_event(small_move_event))

    assert len(intents) == 0


def test_trendline_break_insufficient_data() -> None:
    """Test that strategy needs minimum data points."""
    strategy = TrendlineBreak()
    strategy.configure(
        {
            "lookback_periods": 5,
            "breakout_threshold": 0.02,
            "qty": 1.0,
            "symbol": "ATOM/USDT",
        }
    )

    # Feed only 2 prices (insufficient for regression)
    events = [
        {"symbol": "ATOM/USDT", "price": 10.0, "ts_local_ns": 1000},
        {"symbol": "ATOM/USDT", "price": 10.1, "ts_local_ns": 2000},
    ]

    for event in events:
        intents = list(strategy.on_event(event))
        assert len(intents) == 0


def test_trendline_break_invalid_event() -> None:
    """Test handling of invalid events."""
    strategy = TrendlineBreak()

    # Non-dict event
    intents = list(strategy.on_event("invalid"))
    assert len(intents) == 0

    # Missing price
    intents = list(strategy.on_event({"symbol": "ATOM/USDT"}))
    assert len(intents) == 0
