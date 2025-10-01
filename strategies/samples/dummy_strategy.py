from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.contracts import OrderIntent
from strategies.base import StrategyBase

__all__ = ["DummyStrategy"]


class DummyStrategy(StrategyBase):
    """Dummy strategy for testing registry discovery."""

    strategy_id = "dummy_v1"

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        """No-op strategy for testing."""
        return []
