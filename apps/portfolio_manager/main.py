"""Portfolio manager service orchestrating allocation and rebalancing."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.bus import Bus
from core.config import Config, load_config
from core.contracts import FillEvent
from core.journal import NdjsonJournal
from core.logging import setup_json_logging
from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioSnapshot
from portfolio.position_sizer import PositionSizer
from portfolio.rebalancer import RebalancePlan, Rebalancer
from portfolio.risk_adjusted import RiskAdjustedAllocator
from portfolio.tracker import PortfolioTracker

FILL_TOPIC_DEFAULT = "exec.fill"
SNAPSHOT_TOPIC_DEFAULT = "portfolio.snapshot"


class BusProto(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


@dataclass
class PortfolioManager:
    """High-level coordinator that reacts to fills and triggers rebalances."""

    bus: BusProto
    tracker: PortfolioTracker
    allocator: AllocationCalculator
    rebalancer: Rebalancer
    snapshot_topic: str
    intents_topic: str
    min_rebalance_wait_ns: int
    journal: NdjsonJournal | None = None
    risk_adjuster: RiskAdjustedAllocator | None = None
    performance_history_fn: Callable[[], dict[str, list[float]]] | None = None
    clock_ns: Callable[[], int] = time.time_ns
    _last_rebalance_ns: int = field(default=0, init=False)

    async def process_fill_event(self, event: dict[str, Any]) -> None:
        """Apply a fill and broadcast the updated snapshot."""

        fill = _dict_to_fill(event)
        self.tracker.on_fill(fill)
        if self.journal is not None:
            snapshot_dict = _snapshot_to_dict(self.tracker.get_snapshot())
            self.journal.write_lines([json.dumps(snapshot_dict, separators=(",", ":"))])
        await self.publish_snapshot()

    async def publish_snapshot(self) -> None:
        snapshot_dict = _snapshot_to_dict(self.tracker.get_snapshot())
        await self.bus.publish_json(self.snapshot_topic, snapshot_dict)

    async def maybe_rebalance(self) -> RebalancePlan | None:
        """Trigger a rebalance if drift exceeds thresholds."""

        portfolio_cfg = self.allocator.config
        now = self.clock_ns()
        if (
            now - max(self._last_rebalance_ns, self.tracker.get_last_rebalance_ts())
            < self.min_rebalance_wait_ns
        ):
            return None

        snapshot = self.tracker.get_snapshot()
        strategy_ids = [alloc.strategy_id for alloc in portfolio_cfg.enabled_allocations()]
        current_allocations = {
            strategy_id: self.tracker.get_strategy_capital(strategy_id)
            for strategy_id in strategy_ids
        }
        targets = self.allocator.calculate_targets(current_allocations=current_allocations)
        weights = {
            strategy_id: capital / self.allocator.config.total_capital
            for strategy_id, capital in targets.items()
        }

        if self.risk_adjuster is not None:
            performance_history = (
                self.performance_history_fn() if self.performance_history_fn else {}
            )
            adjusted_weights = self.risk_adjuster.calculate_adjusted_allocations(
                performance_history=performance_history,
                base_allocations=weights,
            )
            targets = {
                strategy_id: adjusted_weights[strategy_id] * self.allocator.config.total_capital
                for strategy_id in adjusted_weights
            }
        drift = self.allocator.calculate_drift(current_allocations, targets)

        if not self.allocator.needs_rebalance(
            drift,
            self.tracker.get_last_rebalance_ts(),
            now,
        ):
            return None

        price_map = {pos.symbol: pos.current_price for pos in snapshot.positions}
        plan = self.rebalancer.create_rebalance_plan(snapshot, price_map)

        if not plan.trades:
            return None

        for trade in plan.trades:
            await self.bus.publish_json(self.intents_topic, _order_intent_to_dict(trade))

        self.tracker.record_rebalance(now)
        self._last_rebalance_ns = now
        return plan


@dataclass
class ManagerConfig:
    config_root: str
    snapshot_topic: str
    fill_topic: str
    rebalance_interval_sec: int
    min_rebalance_wait_sec: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio manager service")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    parser.add_argument(
        "--snapshot-topic",
        default=SNAPSHOT_TOPIC_DEFAULT,
        help="Redis topic for portfolio snapshots",
    )
    parser.add_argument(
        "--fill-topic",
        default=FILL_TOPIC_DEFAULT,
        help="Redis topic for fills",
    )
    parser.add_argument(
        "--rebalance-interval-sec",
        type=int,
        default=60,
        help="Seconds between rebalance checks",
    )
    parser.add_argument(
        "--min-rebalance-wait-sec",
        type=int,
        default=300,
        help="Minimum seconds between rebalances",
    )
    return parser


async def run_manager(config: Config, manager_cfg: ManagerConfig) -> None:
    if config.portfolio is None:
        raise ValueError("Portfolio configuration required for portfolio manager")

    log_dir = Path(config.logging.journal_dir)
    setup_json_logging(str(log_dir))

    bus = Bus(config.redis.url)
    tracker = PortfolioTracker(config.portfolio)
    allocator = AllocationCalculator(config.portfolio)
    sizer = PositionSizer(config.portfolio)
    rebalancer = Rebalancer(allocator, sizer)
    risk_adjuster = RiskAdjustedAllocator(allocator)

    journal = NdjsonJournal(log_dir / "portfolio.ndjson")
    manager = PortfolioManager(
        bus=bus,
        tracker=tracker,
        allocator=allocator,
        rebalancer=rebalancer,
        risk_adjuster=risk_adjuster,
        performance_history_fn=lambda: {},
        snapshot_topic=manager_cfg.snapshot_topic,
        intents_topic=config.redis.topics.intents,
        min_rebalance_wait_ns=manager_cfg.min_rebalance_wait_sec * 1_000_000_000,
        journal=journal,
    )

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async def consume_fills() -> None:
        async for payload in bus.subscribe(manager_cfg.fill_topic):
            await manager.process_fill_event(payload)

    async def periodic_checks() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(manager_cfg.rebalance_interval_sec)
            await manager.maybe_rebalance()
            await manager.publish_snapshot()

    tasks = [
        asyncio.create_task(consume_fills()),
        asyncio.create_task(periodic_checks()),
    ]

    try:
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        journal.close()
        await bus.close()


def _dict_to_fill(event: dict[str, Any]) -> FillEvent:
    return FillEvent(
        order_id=event["order_id"],
        symbol=event["symbol"],
        side=event["side"],
        qty=float(event["qty"]),
        price=float(event["price"]),
        fee=float(event.get("fee", 0.0)),
        ts_fill_ns=int(event["ts_fill_ns"]),
        meta=event.get("meta", {}),
    )


def _order_intent_to_dict(intent: Any) -> dict[str, Any]:
    return {
        "id": intent.id,
        "ts_local_ns": intent.ts_local_ns,
        "strategy_id": intent.strategy_id,
        "symbol": intent.symbol,
        "side": intent.side,
        "type": intent.type,
        "qty": intent.qty,
        "limit_price": intent.limit_price,
        "meta": intent.meta,
    }


def _snapshot_to_dict(snapshot: PortfolioSnapshot) -> dict[str, Any]:
    return {
        "ts_ns": snapshot.ts_ns,
        "portfolio_id": snapshot.portfolio_id,
        "total_equity": snapshot.total_equity,
        "cash": snapshot.cash,
        "positions": [
            {
                "strategy_id": pos.strategy_id,
                "symbol": pos.symbol,
                "qty": pos.qty,
                "avg_entry_price": pos.avg_entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "allocated_capital": pos.allocated_capital,
            }
            for pos in snapshot.positions
        ],
        "last_rebalance_ts": snapshot.last_rebalance_ts,
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI plumbing
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config_root)
    manager_cfg = ManagerConfig(
        config_root=args.config_root,
        snapshot_topic=args.snapshot_topic,
        fill_topic=args.fill_topic,
        rebalance_interval_sec=args.rebalance_interval_sec,
        min_rebalance_wait_sec=args.min_rebalance_wait_sec,
    )
    try:
        asyncio.run(run_manager(config, manager_cfg))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
