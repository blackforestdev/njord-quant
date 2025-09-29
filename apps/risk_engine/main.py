from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from redis.asyncio import Redis

from core.bus import Bus
from core.config import Config, load_config
from core.logging import setup_json_logging


class BusProto(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


@dataclass
class IntentStore:
    redis_url: str | None
    _memory: set[str] = field(default_factory=set)
    _redis: Redis | None = field(default=None, init=False)
    _redis_failed: bool = field(default=False, init=False)

    async def _get_redis(self) -> Redis | None:
        if self.redis_url is None or self._redis_failed:
            return None
        if self._redis is None:
            try:
                self._redis = Redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
            except Exception:
                self._redis_failed = True
                self._redis = None
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def mark_if_new(self, intent_id: str) -> bool:
        redis_client = await self._get_redis()
        if redis_client is not None:
            key = self._redis_key()
            try:
                added = await cast(Awaitable[int], redis_client.sadd(key, intent_id))
                if added:
                    # expire after two days to keep the rolling window
                    await cast(Awaitable[int], redis_client.expire(key, 172800))
                    self._memory.add(intent_id)
                    return True
                return False
            except Exception:
                self._redis_failed = True
                self._redis = None
        if intent_id in self._memory:
            return False
        self._memory.add(intent_id)
        return True

    def _redis_key(self) -> str:
        today = datetime.now(tz=UTC).date().isoformat()
        return f"njord:intents:seen:{today}"


@dataclass
class RiskEngine:
    bus: BusProto
    config: Config
    store: IntentStore

    async def run(self) -> None:
        topic = self.config.redis.topics.intents
        async for payload in self.bus.subscribe(topic):
            await self.handle_intent(payload)

    async def handle_intent(self, payload: dict[str, Any]) -> None:
        intent_id = payload.get("id") or payload.get("intent_id")
        if intent_id is None:
            return

        is_new = await self.store.mark_if_new(intent_id)
        risk_topic = self.config.redis.topics.risk
        if not is_new:
            decision = {
                "intent_id": intent_id,
                "allowed": False,
                "reason": "duplicate-intent",
                "caps": {},
            }
            await self.bus.publish_json(risk_topic, decision)
            return

        decision = {
            "intent_id": intent_id,
            "allowed": True,
            "reason": None,
            "caps": {},
        }
        await self.bus.publish_json(risk_topic, decision)

        order_event = {
            "intent_id": intent_id,
            "venue": payload.get("venue", self.config.exchange.venue),
            "symbol": payload["symbol"],
            "side": payload["side"],
            "type": payload["type"],
            "qty": float(payload["qty"]),
            "limit_price": payload.get("limit_price"),
            "ts_accepted_ns": time.time_ns(),
        }
        await self.bus.publish_json(self.config.redis.topics.orders, order_event)

    async def close(self) -> None:
        await self.store.close()


class BusWrapper(BusProto):
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        await self._bus.publish_json(topic, payload)

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        return self._bus.subscribe(topic)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Njord risk engine")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    return parser


async def _run(config_root: str) -> None:
    cfg = load_config(config_root)
    setup_json_logging(str(Path(cfg.logging.journal_dir)))
    bus = Bus(cfg.redis.url)
    engine = RiskEngine(bus=BusWrapper(bus), config=cfg, store=IntentStore(cfg.redis.url))
    try:
        await engine.run()
    finally:
        await engine.close()
        await bus.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args.config_root))
    except KeyboardInterrupt:  # pragma: no cover
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
