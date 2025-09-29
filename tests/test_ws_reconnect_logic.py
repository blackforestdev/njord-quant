from __future__ import annotations

import asyncio
from typing import Any

import pytest
import structlog

from apps.broker_binanceus.adapter import BinanceUSBroker
from apps.broker_binanceus.backoff import RestRetry


class FakeProExchange:
    def __init__(self) -> None:
        self.calls = 0

    async def watch_orders(self) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls <= 2:
            raise RuntimeError("disconnected")
        return [
            {
                "id": "1",
                "status": "NEW",
                "filled": 0.0,
                "average": None,
                "timestamp": 1,
                "clientOrderId": "NJ-1",
            }
        ]


class DummyLog:
    def __init__(self) -> None:
        self.warn_calls: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **kwargs: Any) -> None:
        self.warn_calls.append((event, kwargs))

    def info(self, *args: Any, **kwargs: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_ws_reconnect_retries_with_backoff() -> None:
    broker = BinanceUSBroker.__new__(BinanceUSBroker)
    broker._exchange = object()
    broker._pro_exchange = FakeProExchange()
    broker._read_only = True
    broker._listen_key = None
    broker._last_cancel_update = None
    broker._rest_retry = RestRetry(
        sleep_fn=lambda _seconds: None,
        logger=structlog.get_logger("test"),
    )

    log = DummyLog()
    broker._log = log

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    stop_event = asyncio.Event()

    async with broker.start_user_stream(
        reconnect_sleep=fake_sleep,
        reconnect_rand=lambda: 0.5,
        reconnect_max_attempts=5,
        reconnect_stop_event=stop_event,
    ) as stream:
        batch = await asyncio.wait_for(stream.__anext__(), timeout=0.2)
        stop_event.set()
        await asyncio.sleep(0)

    assert batch[0].exchange_order_id == "1"
    assert 3 <= broker._pro_exchange.calls <= 5
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(0.5)
    assert sleeps[1] == pytest.approx(1.0)
    assert len(log.warn_calls) == 1
