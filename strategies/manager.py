from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from typing import Any

from core.contracts import PositionSnapshot
from strategies.base import StrategyBase
from strategies.context import BusProto, StrategyContext
from strategies.registry import StrategyRegistry
from telemetry.instrumentation import MetricsEmitter

__all__ = ["StrategyManager"]

logger = logging.getLogger(__name__)


class StrategyManager:
    """Manages strategy lifecycle: loading, reloading, event dispatching."""

    def __init__(
        self, registry: StrategyRegistry, bus: BusProto, metrics: MetricsEmitter | None = None
    ) -> None:
        self._registry = registry
        self._bus = bus
        self._strategies: dict[str, StrategyBase] = {}
        self._config: dict[str, Any] = {}
        self._positions: dict[str, PositionSnapshot] = {}
        self._prices: dict[str, float] = {}
        self._subscriptions: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._metrics = metrics or MetricsEmitter(bus)

    async def load(self, config: dict[str, Any]) -> None:
        """Load strategies from config dict."""
        self._config = config
        strategies_list = config.get("strategies", [])

        for strat_config in strategies_list:
            if not strat_config.get("enabled", True):
                logger.info(f"Skipping disabled strategy: {strat_config.get('id')}")
                continue

            strategy_id = strat_config["id"]
            class_path = strat_config["class"]

            # Extract strategy class name from path
            parts = class_path.rsplit(".", 1)
            if len(parts) != 2:
                logger.error(f"Invalid class path: {class_path}")
                continue

            class_name = parts[1]

            try:
                # Get strategy class from registry
                # For now, assume registry has already discovered strategies
                # and we need to match by strategy_id or load from class path
                strategy_cls = self._load_strategy_class(class_path)

                # Create context (for future use in strategy initialization)
                _ctx = StrategyContext(
                    strategy_id=strategy_id,
                    bus=self._bus,
                    positions=self._positions,
                    prices=self._prices,
                    config=strat_config.get("params", {}),
                )

                # Instantiate strategy
                strategy = strategy_cls()
                strategy.strategy_id = strategy_id

                self._strategies[strategy_id] = strategy
                logger.info(f"Loaded strategy: {strategy_id} ({class_name})")

            except Exception as e:
                logger.error(f"Failed to load strategy {strategy_id}: {e}")
                continue

    def _load_strategy_class(self, class_path: str) -> type[StrategyBase]:
        """Dynamically import and return strategy class."""
        import importlib
        from typing import cast

        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cast(type[StrategyBase], cls)

    async def reload(self) -> None:
        """Hot-reload strategy instances."""
        # Cancel existing subscriptions
        for task in self._subscriptions:
            task.cancel()
        self._subscriptions.clear()

        # Clear strategies
        self._strategies = {}

        # Reload from config
        await self.load(self._config)

        logger.info(f"Reloaded strategies: {list(self._strategies.keys())}")

    async def run(self) -> None:
        """Main event loop: subscribe to events, dispatch to strategies."""
        # Subscribe to event topics per strategy
        for strategy_id, strategy in self._strategies.items():
            strat_config = next(
                (s for s in self._config.get("strategies", []) if s["id"] == strategy_id),
                None,
            )
            if not strat_config:
                continue

            event_patterns = strat_config.get("events", [])
            for pattern in event_patterns:
                task = asyncio.create_task(
                    self._subscribe_and_dispatch(strategy_id, strategy, pattern)
                )
                self._subscriptions.append(task)

        # Wait for stop signal
        await self._stop_event.wait()

        # Cancel all subscriptions
        for task in self._subscriptions:
            task.cancel()

    async def _subscribe_and_dispatch(
        self, strategy_id: str, strategy: StrategyBase, topic: str
    ) -> None:
        """Subscribe to topic and dispatch events to strategy."""
        logger.debug(f"Strategy {strategy_id} subscribing to {topic}")

        try:
            async for event in self._bus.subscribe(topic):
                try:
                    await self._process_event(strategy_id, strategy, event)
                except Exception as e:
                    logger.error(f"Strategy {strategy_id} error on event: {e}", exc_info=True)
                    # Continue processing (graceful degradation)

        except asyncio.CancelledError:
            logger.debug(f"Subscription cancelled for {strategy_id} on {topic}")
            raise

    def stop(self) -> None:
        """Signal manager to stop."""
        self._stop_event.set()

    async def _process_event(self, strategy_id: str, strategy: StrategyBase, event: Any) -> None:
        metrics_enabled = self._metrics.is_enabled()
        start = time.perf_counter()
        try:
            intents_iter = strategy.on_event(event)
        except Exception:
            if metrics_enabled:
                await self._metrics.emit_counter(
                    "njord_strategy_errors_total",
                    1.0,
                    {"strategy_id": strategy_id},
                )
            raise
        intents = list(intents_iter)
        duration = time.perf_counter() - start

        if metrics_enabled:
            await self._metrics.emit_histogram(
                "njord_signal_generation_duration_seconds",
                duration,
                {"strategy_id": strategy_id},
            )
            if intents:
                await self._metrics.emit_counter(
                    "njord_signals_generated_total",
                    float(len(intents)),
                    {"strategy_id": strategy_id},
                )

        for intent in intents:
            intent_dict = asdict(intent)
            await self._bus.publish_json("strat.intent", intent_dict)
            logger.debug(f"Published intent from {strategy_id}: {intent.id}")
