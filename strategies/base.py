from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from core.contracts import OrderIntent

__all__ = ["StrategyBase"]


class StrategyBase(ABC):
    """Base interface for strategy plugins."""

    strategy_id: str

    @abstractmethod
    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        """Handle incoming event and yield zero or more order intents."""
        raise NotImplementedError
