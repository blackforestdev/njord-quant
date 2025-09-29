from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from core.config import Config


class InMemoryBus:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = defaultdict(asyncio.Queue)
        self.published: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.published[topic].append(payload)
        await self._queues[topic].put(payload)

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        queue = self._queues[topic]

        async def generator() -> AsyncIterator[dict[str, Any]]:
            while True:
                item = await queue.get()
                yield item

        return generator()


def build_test_config(journal_dir: Path, symbols: list[str]) -> Config:
    cfg_dict = {
        "app": {"name": "test", "env": "test", "timezone": "UTC"},
        "logging": {"level": "INFO", "json": False, "journal_dir": str(journal_dir)},
        "redis": {
            "url": "redis://localhost:6379/0",
            "topics": {
                "trades": "md.trades.{symbol}",
                "book": "md.book.{symbol}",
                "ticker": "md.ticker.{symbol}",
                "intents": "strat.intent",
                "risk": "risk.decision",
                "orders": "orders.accepted",
                "fills": "fills.new",
            },
        },
        "postgres": {"dsn": "postgresql://user:pass@localhost/db"},
        "exchange": {"venue": "test", "symbols": symbols, "ws_keepalive_sec": 15},
        "risk": {
            "per_order_usd_cap": 250.0,
            "daily_loss_usd_cap": 300.0,
            "orders_per_min_cap": 30,
            "kill_switch_file": str(journal_dir / "halt"),
            "kill_switch_key": "test:halt",
        },
        "paths": {
            "journal_dir": str(journal_dir),
            "experiments_dir": str(journal_dir / "experiments"),
        },
    }
    return cast(Config, Config.model_validate(cfg_dict))
