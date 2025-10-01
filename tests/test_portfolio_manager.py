"""Unit tests for the portfolio manager service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import pytest

from apps.portfolio_manager.main import PortfolioManager
from core.contracts import FillEvent
from core.journal import NdjsonJournal
from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioConfig, StrategyAllocation
from portfolio.position_sizer import PositionSizer
from portfolio.rebalancer import RebalancePlan, Rebalancer
from portfolio.tracker import PortfolioTracker


def _build_portfolio_config() -> PortfolioConfig:
    allocations = (
        StrategyAllocation(strategy_id="alpha", target_weight=0.6),
        StrategyAllocation(strategy_id="beta", target_weight=0.4),
    )
    return PortfolioConfig(
        portfolio_id="test_portfolio",
        allocations=allocations,
        total_capital=100_000.0,
        allow_fractional=True,
    )


@dataclass
class StubJournal:
    lines: list[str]

    def write_lines(self, lines: list[str]) -> None:
        self.lines.extend(lines)

    def close(self) -> None:  # pragma: no cover - compatibility
        pass


class StubBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, payload))

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:  # pragma: no cover
        async def _iter() -> AsyncIterator[dict[str, Any]]:
            if False:  # pragma: no cover - deliberate empty iterator
                yield {}
            return

        return _iter()


@pytest.mark.asyncio
async def test_manager_process_fill_event_records_snapshot() -> None:
    cfg = _build_portfolio_config()
    tracker = PortfolioTracker(cfg)
    allocator = AllocationCalculator(cfg)
    sizer = PositionSizer(cfg)
    rebalancer = Rebalancer(allocator, sizer)

    bus = StubBus()
    journal = StubJournal(lines=[])
    manager = PortfolioManager(
        bus=bus,
        tracker=tracker,
        allocator=allocator,
        rebalancer=rebalancer,
        snapshot_topic="portfolio.snapshot",
        intents_topic="strat.intent",
        min_rebalance_wait_ns=0,
        journal=cast(NdjsonJournal | None, journal),
        clock_ns=lambda: 123,
    )

    event = {
        "order_id": "order-1",
        "symbol": "ATOM/USDT",
        "side": "buy",
        "qty": 100.0,
        "price": 100.0,
        "ts_fill_ns": 1_000,
        "fee": 10.0,
        "meta": {"strategy_id": "alpha"},
    }

    await manager.process_fill_event(event)

    assert journal.lines, "journal should receive snapshot entries"
    snapshot_topic, payload = bus.published[-1]
    assert snapshot_topic == "portfolio.snapshot"
    assert payload["portfolio_id"] == "test_portfolio"


@pytest.mark.asyncio
async def test_manager_maybe_rebalance_publishes_order_intents() -> None:
    cfg = _build_portfolio_config()
    tracker = PortfolioTracker(cfg)
    allocator = AllocationCalculator(cfg)
    sizer = PositionSizer(cfg)
    rebalancer = Rebalancer(allocator, sizer)
    bus = StubBus()

    manager = PortfolioManager(
        bus=bus,
        tracker=tracker,
        allocator=allocator,
        rebalancer=rebalancer,
        snapshot_topic="portfolio.snapshot",
        intents_topic="strat.intent",
        min_rebalance_wait_ns=0,
        journal=None,
        clock_ns=lambda: 5000,
    )

    # Create drift: alpha rallies significantly relative to target.
    buy_fill = FillEvent(
        order_id="order-1",
        symbol="ATOM/USDT",
        side="buy",
        qty=100.0,
        price=100.0,
        fee=0.0,
        ts_fill_ns=1_000,
        meta={"strategy_id": "alpha"},
    )
    tracker.on_fill(buy_fill)
    tracker.update_mark_to_market("alpha", "ATOM/USDT", 150.0, ts_ns=2_000)

    plan = await manager.maybe_rebalance()

    assert isinstance(plan, RebalancePlan)
    assert plan.trades, "rebalance plan should produce trades"
    assert any(topic == "strat.intent" for topic, _ in bus.published)
    assert manager._last_rebalance_ns == 5000
