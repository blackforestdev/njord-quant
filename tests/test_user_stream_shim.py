from __future__ import annotations

import asyncio
import time
from typing import Any, cast

import pytest
import structlog

from apps.broker_binanceus.adapter import BinanceUSBroker
from apps.broker_binanceus.backoff import RestRetry


class FakeExchange:
    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = []

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return [dict(order) for order in self.orders]


def make_broker() -> BinanceUSBroker:
    broker = BinanceUSBroker.__new__(BinanceUSBroker)
    broker._exchange = FakeExchange()
    broker._pro_exchange = None
    broker._read_only = True
    broker._listen_key = None
    broker._rest_retry = RestRetry(
        sleep_fn=lambda _seconds: None, logger=structlog.get_logger("test")
    )
    broker._log = structlog.get_logger("test")
    return broker


@pytest.mark.asyncio
async def test_rest_poll_stream_emits_diff() -> None:
    broker = make_broker()
    fake_exchange = cast(FakeExchange, broker._exchange)

    async with broker.start_user_stream(poll_interval=0.05) as stream:
        collected: list[list[Any]] = []

        async def collector() -> None:
            async for batch in stream:
                collected.append(batch)
                break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.1)
        fake_exchange.orders.append(
            {
                "id": "1",
                "status": "NEW",
                "filled": 0.0,
                "average": None,
                "timestamp": int(time.time() * 1000),
            }
        )
        await asyncio.wait_for(task, timeout=1.0)

    assert collected, "expected at least one batch"
    update = collected[0][0]
    assert update.exchange_order_id == "1"
    assert update.status == "NEW"
