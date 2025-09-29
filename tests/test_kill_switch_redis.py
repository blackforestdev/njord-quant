from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pytest

from core.kill_switch import redis_tripped

F = TypeVar("F", bound=Callable[..., None])


def typed(x: F) -> F:
    return x


@typed(pytest.mark.asyncio)
async def test_redis_tripped_with_fakeredis(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr("redis.asyncio.Redis.from_url", _from_url)

    await fake.set("kill", "1")
    assert await redis_tripped("redis://ignored", "kill") is True

    await fake.set("kill", "0")
    assert await redis_tripped("redis://ignored", "kill") is False
