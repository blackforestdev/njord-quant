from __future__ import annotations

from pathlib import Path
from typing import cast

from redis.asyncio import Redis


def file_tripped(path: str) -> bool:
    """Return True when the on-disk kill switch file exists."""

    return Path(path).exists()


async def redis_tripped(url: str, key: str) -> bool:
    """Return True when Redis key holds the string "1"."""

    client = Redis.from_url(url, encoding="utf-8", decode_responses=True)
    try:
        value = cast(str | None, await client.get(key))
    finally:
        await client.aclose()
    return value == "1"


def trip_file(path: str) -> None:
    """Create the kill switch file, ensuring parent directories exist."""

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.touch(exist_ok=True)


def clear_file(path: str) -> None:
    """Remove the kill switch file if present."""

    file_path = Path(path)
    file_path.unlink(missing_ok=True)
