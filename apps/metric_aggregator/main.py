"""Metric aggregation service main entry point.

This service subscribes to the telemetry.metrics topic, aggregates metrics
into time-based buckets, and publishes to a shared MetricRegistry for
Prometheus scraping.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from core.bus import Bus
from core.config import load_config
from core.logging import setup_json_logging
from telemetry.aggregation import MetricAggregator
from telemetry.registry import MetricRegistry

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser.

    Returns:
        Configured argument parser
    """
    parser = argparse.ArgumentParser(description="Njord metric aggregation service")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    parser.add_argument(
        "--retention-hours",
        type=int,
        default=168,  # 7 days
        help="Metric retention period in hours (default: 168 = 7 days)",
    )
    parser.add_argument(
        "--flush-interval",
        type=int,
        default=60,
        help="Flush interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--grace-period",
        type=int,
        default=300,
        help="Grace period for late metrics in seconds (default: 300 = 5 minutes)",
    )
    return parser


async def run_aggregator(
    config_root: str,
    retention_hours: int,
    flush_interval: int,
    grace_period: int,
) -> None:
    """Run metric aggregator service.

    Args:
        config_root: Config directory path
        retention_hours: Metric retention period
        flush_interval: Flush interval in seconds
        grace_period: Grace period for late metrics
    """
    config = load_config(config_root)
    log_dir = Path(config.logging.journal_dir)
    setup_json_logging(str(log_dir))

    logger.info(
        "metric_aggregator_starting",
        extra={
            "retention_hours": retention_hours,
            "flush_interval_seconds": flush_interval,
            "grace_period_seconds": grace_period,
        },
    )

    # Create shared registry (will be used by PrometheusExporter in production)
    registry = MetricRegistry()

    # Create bus connection
    bus = Bus(config.redis.url)

    # Create and run aggregator
    aggregator = MetricAggregator(
        bus=bus,
        journal_dir=log_dir / "metrics",
        registry=registry,
        retention_hours=retention_hours,
        flush_interval_seconds=flush_interval,
        grace_period_seconds=grace_period,
    )

    try:
        logger.info("metric_aggregator_ready", extra={"bus_url": config.redis.url})
        await aggregator.run()
    except KeyboardInterrupt:
        logger.info("metric_aggregator_shutdown")
    finally:
        await bus.close()


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments

    Returns:
        Exit code
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        asyncio.run(
            run_aggregator(
                config_root=args.config_root,
                retention_hours=args.retention_hours,
                flush_interval=args.flush_interval,
                grace_period=args.grace_period,
            )
        )
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
