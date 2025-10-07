from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from core.bus import Bus
from core.config import load_config
from core.logging import setup_json_logging
from strategies.manager import StrategyManager
from strategies.registry import StrategyRegistry
from telemetry.instrumentation import MetricsEmitter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strategy runner service")
    parser.add_argument(
        "--config",
        default="./config/base.yaml",
        help="Path to base config file (default: ./config/base.yaml)",
    )
    parser.add_argument(
        "--strategies",
        default="./config/strategies.yaml",
        help="Path to strategies config file (default: ./config/strategies.yaml)",
    )
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Load base config
    config = load_config(Path(args.config).parent)

    # Setup logging
    log_dir = config.logging.journal_dir
    logger = setup_json_logging(str(log_dir))
    logger.info("Strategy runner service starting", config_path=args.config)

    # Load strategies config
    strategies_path = Path(args.strategies)
    if not strategies_path.exists():
        logger.error("Strategies config not found", path=str(strategies_path))
        return

    with open(strategies_path) as f:
        strategies_config = yaml.safe_load(f)

    logger.info(
        "Loaded strategies config",
        path=str(strategies_path),
        num_strategies=len(strategies_config.get("strategies", [])),
    )

    # Initialize bus
    bus = Bus(config.redis.url)

    try:
        # Initialize registry and discover strategies
        registry = StrategyRegistry()
        registry.discover("strategies.samples")

        logger.info("Discovered strategies", count=len(registry._strategies))

        # Initialize manager
        metrics = MetricsEmitter(bus)
        manager = StrategyManager(registry, bus, metrics)

        # Load strategies from config
        await manager.load(strategies_config)

        logger.info(
            "Loaded strategies into manager",
            active_strategies=list(manager._strategies.keys()),
        )

        # Run manager (blocks until stopped)
        logger.info("Starting strategy manager event loop")
        await manager.run()

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as e:
        logger.error("Strategy runner error", error=str(e), exc_info=True)
        raise
    finally:
        await bus.close()
        logger.info("Strategy runner service stopped")


if __name__ == "__main__":
    asyncio.run(main())
