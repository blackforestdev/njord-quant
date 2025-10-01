from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from core.contracts import PositionSnapshot

__all__ = ["BusProto", "StrategyContext"]


class BusProto(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


@dataclass(frozen=True)
class StrategyContext:
    """Injected state container for strategy plugins."""

    strategy_id: str
    bus: BusProto
    positions: dict[str, PositionSnapshot]
    prices: dict[str, float]
    config: dict[str, Any]
