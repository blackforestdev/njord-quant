from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from redis.asyncio import Redis


class Bus:
    """Async publish/subscribe helper backed by Redis."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Redis | None = None

    async def _get_client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(self._url, encoding="utf-8", decode_responses=True)
        return self._client

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        client = await self._get_client()
        data = json.dumps(payload, separators=(",", ":"))
        await client.publish(topic, data)

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        async def stream() -> AsyncIterator[dict[str, Any]]:
            client = await self._get_client()
            pubsub = cast(Any, client.pubsub())
            await pubsub.subscribe(topic)
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    payload = json.loads(data)
                    yield payload
            finally:
                await pubsub.unsubscribe(topic)
                await pubsub.aclose()

        return stream()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
