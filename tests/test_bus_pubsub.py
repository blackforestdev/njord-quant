from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from typing import TypeVar

import pytest

from core.bus import Bus

F = TypeVar("F", bound=Callable[..., None])


def typed(x: F) -> F:
    return x


@typed(pytest.mark.asyncio)
async def test_publish_and_receive_round_trip() -> None:
    if os.getenv("REDIS_SKIP") == "1":
        pytest.skip("redis tests disabled")

    try:
        from redis.asyncio import Redis
    except ModuleNotFoundError:  # pragma: no cover
        pytest.skip("redis library not installed")

    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = Redis.from_url(url)
    try:
        await asyncio.wait_for(client.ping(), timeout=1)
    except Exception as exc:  # pragma: no cover - depends on local redis
        pytest.skip(f"redis not available: {exc}")
    finally:
        await client.aclose()

    bus = Bus(url)
    topic = f"test.bus.{uuid.uuid4().hex}"
    received: list[dict[str, int]] = []

    async def consume_one() -> None:
        async for item in bus.subscribe(topic):
            received.append(item)
            break

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0.05)
    await bus.publish_json(topic, {"x": 1})

    await asyncio.wait_for(task, timeout=5)
    assert received == [{"x": 1}]

    await bus.close()
