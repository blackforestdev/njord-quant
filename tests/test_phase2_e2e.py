from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

from apps.paper_trader.main import PaperTrader
from apps.risk_engine.main import IntentStore, RiskEngine
from tests.utils import InMemoryBus, build_test_config

F = TypeVar("F", bound=Callable[..., None])


def typed(x: F) -> F:
    return x


async def wait_for(
    condition: Callable[[], bool], *, timeout: float = 1.0, interval: float = 0.01
) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if condition():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not met before timeout")


@typed(pytest.mark.asyncio)
async def test_phase2_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        from fakeredis.aioredis import FakeRedis
    except ModuleNotFoundError:
        pytest.skip("fakeredis.aioredis not installed")

    fake = FakeRedis(decode_responses=True)

    async def _aclose() -> None:
        return None

    monkeypatch.setattr(fake, "aclose", _aclose, raising=False)

    def _from_url(
        url: str, *, encoding: str | None = None, decode_responses: bool = False
    ) -> FakeRedis:
        return fake

    monkeypatch.setattr("apps.risk_engine.main.Redis.from_url", _from_url)

    bus = InMemoryBus()
    cfg = build_test_config(tmp_path, ["ATOMUSDT"])
    store = IntentStore(redis_url="redis://fake")
    engine = RiskEngine(bus=bus, config=cfg, store=store)
    trader = PaperTrader(bus=bus, config=cfg, journal_dir=Path(cfg.logging.journal_dir))

    risk_task = asyncio.create_task(engine.run())
    paper_task = asyncio.create_task(trader.run())

    try:
        trades_topic = cfg.redis.topics.trades.format(symbol="ATOMUSDT")
        await bus.publish_json(trades_topic, {"price": 10.0})

        await wait_for(lambda: trader.last_trade_price.get("ATOMUSDT") == 10.0)

        intent_topic = cfg.redis.topics.intents
        intent = {
            "id": "intent-1",
            "symbol": "ATOMUSDT",
            "side": "buy",
            "type": "market",
            "qty": 1.0,
            "limit_price": None,
            "strategy_id": "paper-test",
            "ts_local_ns": 1,
        }
        await bus.publish_json(intent_topic, intent)

        risk_topic = cfg.redis.topics.risk
        orders_topic = cfg.redis.topics.orders

        await wait_for(lambda: bool(bus.published[risk_topic]))
        await wait_for(lambda: bool(bus.published[orders_topic]))
        await wait_for(lambda: bool(bus.published["fills.new"]))
        await wait_for(lambda: bool(bus.published["positions.snapshot"]))

        decision = bus.published[risk_topic][-1]
        assert decision["allowed"] is True
        assert decision["intent_id"] == "intent-1"

        order_event = bus.published[orders_topic][-1]
        assert order_event["intent_id"] == "intent-1"
        assert order_event["symbol"] == "ATOMUSDT"

        fill_event = bus.published["fills.new"][-1]
        assert pytest.approx(fill_event["price"], rel=1e-9) == 10.0
        assert pytest.approx(fill_event["qty"], rel=1e-9) == 1.0

        snapshot = bus.published["positions.snapshot"][-1]
        assert pytest.approx(snapshot["qty"], rel=1e-9) == 1.0
        assert pytest.approx(snapshot["avg_price"], rel=1e-9) == 10.0
    finally:
        risk_task.cancel()
        paper_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await risk_task
            await paper_task
        await engine.close()
        await trader.close()
