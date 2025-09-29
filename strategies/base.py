from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.contracts import OrderIntent


class StrategyBase:
    strategy_id: str = "base"

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        """Handle an incoming event and yield zero or more order intents."""

        intents: list[OrderIntent] = []
        return intents
