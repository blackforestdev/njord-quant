from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from core.contracts import OrderIntent
from strategies.base import StrategyBase
from strategies.registry import StrategyRegistry


class TestStrategyA(StrategyBase):
    strategy_id = "test_a"

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        return []


class TestStrategyB(StrategyBase):
    strategy_id = "test_b"

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        return []


class NoIdStrategy(StrategyBase):
    """Strategy without strategy_id attribute."""

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        return []


def test_register_strategy() -> None:
    registry = StrategyRegistry()
    registry.register(TestStrategyA)

    assert registry.get("test_a") is TestStrategyA


def test_register_multiple_strategies() -> None:
    registry = StrategyRegistry()
    registry.register(TestStrategyA)
    registry.register(TestStrategyB)

    assert registry.get("test_a") is TestStrategyA
    assert registry.get("test_b") is TestStrategyB


def test_get_nonexistent_strategy_raises() -> None:
    registry = StrategyRegistry()

    with pytest.raises(KeyError, match="Strategy not found: nonexistent"):
        registry.get("nonexistent")


def test_register_without_id_raises() -> None:
    registry = StrategyRegistry()

    with pytest.raises(ValueError, match="missing strategy_id"):
        registry.register(NoIdStrategy)


def test_discover_sample_strategies() -> None:
    registry = StrategyRegistry()
    registry.discover("strategies.samples")

    # Should have discovered DummyStrategy
    dummy_cls = registry.get("dummy_v1")
    assert dummy_cls.strategy_id == "dummy_v1"


def test_discover_nonexistent_package() -> None:
    """Should log warning but not raise."""
    registry = StrategyRegistry()
    registry.discover("nonexistent.package")
    # No exception, just warning logged


def test_discover_invalid_module() -> None:
    """Should skip modules that fail to import."""
    registry = StrategyRegistry()
    # This package exists but has no strategies
    registry.discover("core")
    # No exception, should handle gracefully
