from __future__ import annotations

from typing import Any

import pytest
import structlog

from apps.broker_binanceus.backoff import RestRetry


class FakeRateLimit(Exception):
    def __init__(self, headers: dict[str, Any]) -> None:
        super().__init__("rate limited")
        self.http_status = 429
        self.headers = headers


def test_rest_retry_honors_retry_after() -> None:
    delays: list[float] = []

    def sleep(delay: float) -> None:
        delays.append(delay)

    retry = RestRetry(
        sleep_fn=sleep,
        rand_fn=lambda: 0.7,
        logger=structlog.get_logger("test"),
    )

    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FakeRateLimit({"Retry-After": "1.5"})
        return "ok"

    result = retry.call(flaky)
    assert result == "ok"
    assert calls == 2
    assert len(delays) == 1
    assert delays[0] == pytest.approx(1.5)
