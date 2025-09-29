from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import structlog

try:  # pragma: no cover - optional dependency
    import ccxt
except ModuleNotFoundError:  # pragma: no cover - testing environments
    ccxt = None


T = TypeVar("T")


def _parse_retry_after(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class RestRetryConfig:
    max_attempts: int = 5
    base_delay_s: float = 0.5
    max_delay_s: float = 10.0


class RestRetry:
    def __init__(
        self,
        *,
        config: RestRetryConfig | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        rand_fn: Callable[[], float] = random.random,
        logger: Any | None = None,
    ) -> None:
        self._config = config or RestRetryConfig()
        self._sleep = sleep_fn or time.sleep
        self._rand = rand_fn
        self._log = logger or structlog.get_logger("broker.binanceus.rest")

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        attempts = 0
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                attempts += 1
                if not self._should_retry(exc) or attempts >= self._config.max_attempts:
                    raise
                delay = self._compute_delay(attempts, exc)
                if delay > 0:
                    self._log.warning(
                        "rest_retry", attempt=attempts, delay=round(delay, 3), error=str(exc)
                    )
                    self._sleep(delay)

    def _should_retry(self, exc: Exception) -> bool:
        status = getattr(exc, "http_status", None) or getattr(exc, "status", None)
        if isinstance(status, int) and status in {418, 429}:
            return True
        headers = self._extract_headers(exc)
        if headers and "Retry-After" in headers:
            return True
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        if ccxt is not None:
            network_error_cls = getattr(ccxt, "NetworkError", None)
            if network_error_cls is not None and isinstance(exc, network_error_cls):
                return True
        return False

    def _compute_delay(self, attempts: int, exc: Exception) -> float:
        headers = self._extract_headers(exc)
        if headers:
            retry_after = _parse_retry_after(headers.get("Retry-After"))
            if retry_after is not None:
                return max(0.0, float(retry_after))
        cap = min(
            self._config.max_delay_s,
            self._config.base_delay_s * (2 ** max(attempts - 1, 0)),
        )
        rand_value = float(self._rand())
        return float(max(0.0, rand_value * cap))

    @staticmethod
    def _extract_headers(exc: Exception) -> Mapping[str, Any] | None:
        headers = getattr(exc, "headers", None)
        if isinstance(headers, Mapping):
            return headers
        response = getattr(exc, "response", None)
        if response is not None:
            response_headers = getattr(response, "headers", None)
            if isinstance(response_headers, Mapping):
                return response_headers
        return None
