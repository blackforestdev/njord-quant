from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from .types import OrderIntent


class Clock(Protocol):
    """Minimal clock interface strategies can rely on."""

    def now(self) -> float: ...


@dataclass(slots=True)
class SymbolConfig:
    """Per-symbol configuration exposed to strategies."""

    symbol: str


@dataclass(slots=True)
class Context:
    """Runtime context passed to strategies."""

    clock: Clock
    symbols: dict[str, SymbolConfig]
    risk_caps: dict[str, Any]
    dry_run: bool


class Strategy(ABC):
    """Base Strategy definition."""

    def __init__(self) -> None:
        self._started = False

    def on_start(self, context: Context | None = None) -> None:
        """Called once before event processing begins."""

        self._started = True

    def on_stop(self) -> None:
        """Called once when strategy is shutting down."""

        self._started = False

    @abstractmethod
    def on_event(self, event: dict[str, Any]) -> Iterable[OrderIntent]:
        """Process an event and yield any resultant order intents."""
