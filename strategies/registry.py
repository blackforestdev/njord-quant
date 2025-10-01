from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strategies.base import StrategyBase

__all__ = ["StrategyRegistry"]

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry for strategy plugins."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[StrategyBase]] = {}

    def register(self, strategy_class: type[StrategyBase]) -> None:
        """Register a strategy class by its strategy_id."""
        if not hasattr(strategy_class, "strategy_id"):
            raise ValueError(f"{strategy_class.__name__} missing strategy_id attribute")

        strategy_id = strategy_class.strategy_id
        if strategy_id in self._strategies:
            logger.warning(f"Overwriting existing strategy: {strategy_id}")

        self._strategies[strategy_id] = strategy_class
        logger.debug(f"Registered strategy: {strategy_id} ({strategy_class.__name__})")

    def get(self, strategy_id: str) -> type[StrategyBase]:
        """Retrieve a strategy class by ID."""
        if strategy_id not in self._strategies:
            raise KeyError(f"Strategy not found: {strategy_id}")
        return self._strategies[strategy_id]

    def discover(self, package: str = "strategies.samples") -> None:
        """Auto-discover strategies in package."""
        try:
            pkg = importlib.import_module(package)
        except ImportError as e:
            logger.warning(f"Failed to import package {package}: {e}")
            return

        # Import all modules in package
        if not hasattr(pkg, "__path__"):
            logger.warning(f"Package {package} has no __path__, skipping discovery")
            return

        for _importer, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
            full_name = f"{package}.{modname}"
            try:
                mod = importlib.import_module(full_name)
            except Exception as e:
                logger.warning(f"Failed to import {full_name}: {e}")
                continue

            # Find StrategyBase subclasses
            from strategies.base import StrategyBase

            for _name, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, StrategyBase) and obj is not StrategyBase:
                    try:
                        self.register(obj)
                    except ValueError as e:
                        logger.warning(f"Failed to register {obj.__name__}: {e}")
