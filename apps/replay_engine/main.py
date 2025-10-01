"""OHLCV replay engine for backtesting and analysis.

Replays historical OHLCV bars from journals at controlled speed.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from core.bus import Bus
from core.config import load_config
from core.journal_reader import JournalReader
from core.logging import setup_json_logging


class ReplayEngine:
    """Replays historical OHLCV bars from journals."""

    def __init__(
        self,
        journal_dir: Path,
        bus: Bus,
        speed_multiplier: float = 1.0,
    ) -> None:
        """Initialize replay engine.

        Args:
            journal_dir: Directory containing journal files
            bus: Redis bus for publishing events
            speed_multiplier: Speed control (1.0 = real-time, 10.0 = 10x faster, 0 = max speed)
        """
        self.journal_dir = journal_dir
        self.bus = bus
        self.speed_multiplier = speed_multiplier
        self.reader = JournalReader(journal_dir)

    async def replay(
        self,
        symbol: str,
        timeframe: str,
        start_ns: int,
        end_ns: int,
    ) -> int:
        """Replay bars for a symbol/timeframe within time range.

        Args:
            symbol: Trading symbol (e.g., "ATOM/USDT")
            timeframe: Timeframe (e.g., "1m", "5m")
            start_ns: Start timestamp (epoch nanoseconds)
            end_ns: End timestamp (epoch nanoseconds)

        Returns:
            Number of bars replayed
        """
        bars = self.reader.read_bars(symbol, timeframe, start_ns, end_ns)

        count = 0
        last_ts = None

        for bar in bars:
            # Calculate delay based on speed multiplier
            if last_ts is not None and self.speed_multiplier > 0:
                time_delta_ns = bar.ts_open - last_ts
                delay_seconds = (time_delta_ns / 1_000_000_000) / self.speed_multiplier
                await asyncio.sleep(delay_seconds)

            # Publish bar to bus
            topic = f"md.ohlcv.{timeframe}.{symbol}"
            bar_dict = asdict(bar)
            await self.bus.publish_json(topic, bar_dict)

            last_ts = bar.ts_open
            count += 1

        return count

    async def replay_multiple(
        self,
        symbols: list[str],
        timeframe: str,
        start_ns: int,
        end_ns: int,
    ) -> dict[str, int]:
        """Replay bars for multiple symbols concurrently.

        Args:
            symbols: List of trading symbols
            timeframe: Timeframe (e.g., "1m", "5m")
            start_ns: Start timestamp (epoch nanoseconds)
            end_ns: End timestamp (epoch nanoseconds)

        Returns:
            Dict mapping symbol to count of bars replayed
        """
        tasks = [self.replay(symbol, timeframe, start_ns, end_ns) for symbol in symbols]

        results = await asyncio.gather(*tasks)

        return dict(zip(symbols, results, strict=True))


def parse_timestamp(ts_str: str) -> int:
    """Parse ISO timestamp to epoch nanoseconds.

    Args:
        ts_str: ISO 8601 timestamp (e.g., "2025-09-01T00:00:00Z")

    Returns:
        Epoch nanoseconds

    Raises:
        ValueError: If timestamp format is invalid
    """
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        epoch_seconds = dt.timestamp()
        return int(epoch_seconds * 1_000_000_000)
    except (ValueError, AttributeError) as e:
        raise ValueError(
            f"Invalid timestamp format: {ts_str}. "
            f"Expected ISO 8601 format (e.g., 2025-09-01T00:00:00Z)"
        ) from e


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OHLCV replay engine - Replay historical market data from journals",
        epilog="Example: python -m apps.replay_engine --symbol ATOM/USDT --timeframe 1m "
        "--start 2025-09-01T00:00:00Z --end 2025-09-30T23:59:59Z --speed 10x",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbol",
        required=True,
        metavar="SYM",
        help="Trading symbol (e.g., ATOM/USDT, BTC/USDT)",
    )
    parser.add_argument(
        "--timeframe",
        default="1m",
        metavar="TF",
        help="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d (default: 1m)",
    )
    parser.add_argument(
        "--start",
        required=True,
        metavar="TS",
        help="Start timestamp in ISO 8601 format (e.g., 2025-09-01T00:00:00Z)",
    )
    parser.add_argument(
        "--end",
        required=True,
        metavar="TS",
        help="End timestamp in ISO 8601 format (e.g., 2025-09-30T23:59:59Z)",
    )
    parser.add_argument(
        "--speed",
        default="1x",
        metavar="MULT",
        help="Replay speed multiplier: 1x, 10x, 100x, max (default: 1x)",
    )
    parser.add_argument(
        "--config",
        default="./config/base.yaml",
        metavar="PATH",
        help="Path to base config file (default: ./config/base.yaml)",
    )
    return parser


def parse_speed(speed_str: str) -> float:
    """Parse speed string to multiplier.

    Args:
        speed_str: Speed string (e.g., "1x", "10x", "100x", "max")

    Returns:
        Speed multiplier (0 = max speed)

    Raises:
        ValueError: If speed format is invalid or negative
    """
    speed_str = speed_str.lower().strip()
    if speed_str == "max":
        return 0.0

    try:
        multiplier = float(speed_str[:-1]) if speed_str.endswith("x") else float(speed_str)

        if multiplier < 0:
            raise ValueError("Speed multiplier cannot be negative")

        return multiplier
    except ValueError as e:
        raise ValueError(
            f"Invalid speed format: {speed_str}. Expected format like '1x', '10x', '100x', or 'max'"
        ) from e


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        # Parse timestamps
        start_ns = parse_timestamp(args.start)
        end_ns = parse_timestamp(args.end)

        # Validate time range
        if start_ns >= end_ns:
            parser.error("Start time must be before end time")

        # Parse speed
        speed_multiplier = parse_speed(args.speed)
    except ValueError as e:
        parser.error(str(e))

    # Load config
    config = load_config(Path(args.config).parent)

    # Setup logging
    logger = setup_json_logging(str(config.logging.journal_dir))
    logger.info(
        "Replay engine starting",
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        speed=args.speed,
    )

    # Initialize bus
    bus = Bus(config.redis.url)

    try:
        # Create replay engine
        journal_dir = Path(config.logging.journal_dir)
        engine = ReplayEngine(journal_dir, bus, speed_multiplier)

        # Replay
        logger.info("Starting replay", symbol=args.symbol, timeframe=args.timeframe)

        count = await engine.replay(args.symbol, args.timeframe, start_ns, end_ns)

        logger.info(
            "Replay complete",
            symbol=args.symbol,
            timeframe=args.timeframe,
            bars_replayed=count,
        )

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as e:
        logger.error("Replay error", error=str(e), exc_info=True)
        raise
    finally:
        await bus.close()
        logger.info("Replay engine stopped")


if __name__ == "__main__":
    asyncio.run(main())
