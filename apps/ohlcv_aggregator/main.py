from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from pathlib import Path

from core.bus import Bus
from core.config import load_config
from core.contracts import OHLCVBar
from core.logging import setup_json_logging


class TradeAggregator:
    """Aggregates trades into OHLCV bars for a specific timeframe."""

    def __init__(self, symbol: str, timeframe: str) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.timeframe_ns = self._parse_timeframe(timeframe)

        # Current bar state
        self.current_bar_start: int | None = None
        self.open_price: float | None = None
        self.high_price: float | None = None
        self.low_price: float | None = None
        self.close_price: float | None = None
        self.volume: float = 0.0
        self.last_close: float | None = None

    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe string to nanoseconds."""
        if timeframe == "1m":
            return 60 * 1_000_000_000
        elif timeframe == "5m":
            return 5 * 60 * 1_000_000_000
        elif timeframe == "15m":
            return 15 * 60 * 1_000_000_000
        elif timeframe == "1h":
            return 60 * 60 * 1_000_000_000
        elif timeframe == "4h":
            return 4 * 60 * 60 * 1_000_000_000
        elif timeframe == "1d":
            return 24 * 60 * 60 * 1_000_000_000
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    def _get_bar_start(self, timestamp_ns: int) -> int:
        """Get the start timestamp of the bar containing this timestamp."""
        return (timestamp_ns // self.timeframe_ns) * self.timeframe_ns

    def add_trade(self, price: float, qty: float, timestamp_ns: int) -> OHLCVBar | None:
        """Add a trade to the aggregator. Returns completed bar if time window closes."""
        bar_start = self._get_bar_start(timestamp_ns)

        # Check if we're starting a new bar
        if self.current_bar_start is None:
            # First trade ever
            self.current_bar_start = bar_start
            self.open_price = price
            self.high_price = price
            self.low_price = price
            self.close_price = price
            self.volume = qty
            return None

        elif bar_start > self.current_bar_start:
            # Time window closed, emit completed bar
            completed_bar = OHLCVBar(
                symbol=self.symbol,
                timeframe=self.timeframe,
                ts_open=self.current_bar_start,
                ts_close=self.current_bar_start + self.timeframe_ns,
                open=self.open_price or 0.0,
                high=self.high_price or 0.0,
                low=self.low_price or 0.0,
                close=self.close_price or 0.0,
                volume=self.volume,
            )

            # Save last close for gap handling
            self.last_close = self.close_price

            # Start new bar with current trade
            self.current_bar_start = bar_start
            self.open_price = price
            self.high_price = price
            self.low_price = price
            self.close_price = price
            self.volume = qty

            return completed_bar

        else:
            # Same bar, update OHLC
            if self.high_price is None or price > self.high_price:
                self.high_price = price
            if self.low_price is None or price < self.low_price:
                self.low_price = price
            self.close_price = price
            self.volume += qty
            return None

    def check_gap(self, current_time_ns: int) -> list[OHLCVBar]:
        """Check for gaps and emit bars with repeated close prices."""
        if self.current_bar_start is None or self.last_close is None:
            return []

        bars = []
        expected_bar_start = self.current_bar_start + self.timeframe_ns

        while expected_bar_start < current_time_ns:
            # Emit gap bar with repeated close
            gap_bar = OHLCVBar(
                symbol=self.symbol,
                timeframe=self.timeframe,
                ts_open=expected_bar_start,
                ts_close=expected_bar_start + self.timeframe_ns,
                open=self.last_close,
                high=self.last_close,
                low=self.last_close,
                close=self.last_close,
                volume=0.0,
            )
            bars.append(gap_bar)
            expected_bar_start += self.timeframe_ns

        return bars


class MultiTimeframeAggregator:
    """Aggregates trades into multiple timeframes concurrently."""

    def __init__(self, symbol: str, timeframes: list[str]) -> None:
        self.symbol = symbol
        self.timeframes = timeframes
        self.aggregators = {tf: TradeAggregator(symbol, tf) for tf in timeframes}

        # Track 1m bars for deriving higher timeframes
        self.minute_bars: list[OHLCVBar] = []

    def add_trade(self, price: float, qty: float, timestamp_ns: int) -> dict[str, OHLCVBar]:
        """Add trade to all aggregators. Returns dict of completed bars by timeframe."""
        completed_bars: dict[str, OHLCVBar] = {}

        # Always aggregate from trades for 1m
        if "1m" in self.aggregators:
            bar = self.aggregators["1m"].add_trade(price, qty, timestamp_ns)
            if bar:
                completed_bars["1m"] = bar
                self.minute_bars.append(bar)

        # For higher timeframes, derive from 1m bars if available
        for tf in self.timeframes:
            if tf == "1m":
                continue

            # Use trade-based aggregation as fallback
            bar = self.aggregators[tf].add_trade(price, qty, timestamp_ns)
            if bar:
                completed_bars[tf] = bar

        return completed_bars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OHLCV aggregator service")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. ATOM/USDT")
    parser.add_argument(
        "--timeframes",
        default="1m",
        help="Comma-separated timeframes (default: 1m). Example: 1m,5m,15m,1h",
    )
    parser.add_argument(
        "--config",
        default="./config/base.yaml",
        help="Path to base config file (default: ./config/base.yaml)",
    )
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Parse timeframes
    timeframes = [tf.strip() for tf in args.timeframes.split(",")]

    # Load config
    config = load_config(Path(args.config).parent)

    # Setup logging
    logger = setup_json_logging(str(config.logging.journal_dir))
    logger.info("OHLCV aggregator starting", symbol=args.symbol, timeframes=timeframes)

    # Initialize bus
    bus = Bus(config.redis.url)

    try:
        # Create multi-timeframe aggregator
        aggregator = MultiTimeframeAggregator(args.symbol, timeframes)

        # Subscribe to trades
        trade_topic = f"md.trades.{args.symbol}"

        logger.info("Subscribing to trades", topic=trade_topic, timeframes=timeframes)

        async for msg in bus.subscribe(trade_topic):
            # Extract trade data
            price = msg.get("price")
            qty = msg.get("qty") or msg.get("amount", 0.0)
            timestamp_ns = msg.get("ts_local_ns", 0)

            if price is None:
                continue

            # Add trade to all aggregators
            completed_bars = aggregator.add_trade(price, qty, timestamp_ns)

            # Publish completed bars
            for timeframe, bar in completed_bars.items():
                bar_topic = f"md.ohlcv.{timeframe}.{args.symbol}"
                bar_dict = asdict(bar)
                await bus.publish_json(bar_topic, bar_dict)
                logger.debug(
                    "Published bar",
                    symbol=args.symbol,
                    timeframe=timeframe,
                    close=bar.close,
                )

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as e:
        logger.error("Aggregator error", error=str(e), exc_info=True)
        raise
    finally:
        await bus.close()
        logger.info("OHLCV aggregator stopped")


if __name__ == "__main__":
    asyncio.run(main())
