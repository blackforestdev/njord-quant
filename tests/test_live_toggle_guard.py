from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
import structlog

from apps.broker_binanceus.main import OrderEngine
from core.broker import BrokerOrderAck, BrokerOrderReq
from core.journal import NdjsonJournal
from tests.utils import InMemoryBus, build_test_config


class FakeBroker:
    def __init__(self) -> None:
        self._read_only = True
        self.requests: list[BrokerOrderReq] = []

    def place(self, req: BrokerOrderReq) -> BrokerOrderAck:
        self.requests.append(req)
        return BrokerOrderAck(
            client_order_id=req.client_order_id,
            exchange_order_id="EX-1",
            ts_ns=time.time_ns(),
        )


async def _noop(_: str) -> None:
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_live_toggle_blocks_and_echo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NJORD_ENABLE_LIVE", raising=False)

    async def fake_redis(*_: Any) -> bool:
        return False

    monkeypatch.setattr("core.kill_switch.redis_tripped", fake_redis)

    cfg = build_test_config(journal_dir=tmp_path, symbols=["ATOM/USDT"])
    cfg.app.env = "dev"

    bus = InMemoryBus()
    broker = FakeBroker()
    orders_journal = NdjsonJournal(tmp_path / "orders.ndjson")
    acks_journal = NdjsonJournal(tmp_path / "acks.ndjson")

    engine = OrderEngine(
        broker=broker,
        bus=bus,
        config=cfg,
        log=structlog.get_logger("test"),
        orders_journal=orders_journal,
        acks_journal=acks_journal,
        add_inflight=_noop,
        last_trade_price={},
        live_enabled=False,
    )

    event = {
        "intent_id": "intent-1",
        "ts_accepted_ns": time.time_ns(),
        "strategy_id": "alpha",
        "symbol": "ATOM/USDT",
        "side": "buy",
        "type": "limit",
        "qty": 1.0,
        "limit_price": 1.5,
    }

    try:
        await engine.handle_event(event)
    finally:
        orders_journal.close()
        acks_journal.close()

    assert not broker.requests
    echo_messages = bus.published["broker.echo"]
    assert len(echo_messages) == 1
    payload = echo_messages[0]
    assert payload["intent_id"] == "intent-1"
    assert payload["symbol"] == "ATOM/USDT"
    assert payload["qty"] == pytest.approx(1.0)
    assert payload["limit_price"] == pytest.approx(1.5)
    assert payload["client_order_id"].startswith("NJ-")
    assert "risk.decisions" not in bus.published or not bus.published["risk.decisions"]
