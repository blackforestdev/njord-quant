from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

from apps.risk_engine.main import IntentStore, RiskEngine
from tests.utils import InMemoryBus, build_test_config

F = TypeVar("F", bound=Callable[..., None])


def typed(x: F) -> F:
    return x


@typed(pytest.mark.asyncio)
async def test_duplicate_intents_only_once(tmp_path: Path) -> None:
    bus = InMemoryBus()
    cfg = build_test_config(tmp_path, ["ATOM/USDT"])
    store = IntentStore(redis_url=None)
    engine = RiskEngine(bus=bus, config=cfg, store=store)

    intent = {
        "id": "intent-1",
        "symbol": "ATOM/USDT",
        "side": "buy",
        "type": "market",
        "qty": 1.0,
        "limit_price": None,
        "strategy_id": "s1",
        "ts_local_ns": 1,
    }

    await engine.handle_intent(intent)
    await engine.handle_intent(intent)

    orders_topic = cfg.redis.topics.orders
    risk_topic = cfg.redis.topics.risk

    assert len(bus.published[orders_topic]) == 1
    assert bus.published[risk_topic][-1]["allowed"] is False

    await engine.close()
