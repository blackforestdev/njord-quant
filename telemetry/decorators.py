"""Decorators for automatic metrics instrumentation."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from telemetry.instrumentation import MetricsEmitter

F = TypeVar("F", bound=Callable[..., Any])


def count_calls(
    emitter: MetricsEmitter,
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> Callable[[F], F]:
    """Decorator to count function calls.

    Args:
        emitter: MetricsEmitter instance
        metric_name: Name of the counter metric
        labels: Static labels to attach to metric

    Returns:
        Decorator function

    Example:
        @count_calls(emitter, "njord_function_calls_total", {"service": "risk_engine"})
        async def handle_intent(self, intent: OrderIntent) -> None:
            ...
    """

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError(f"count_calls can only decorate callable, got {type(func)}")

        # Handle both async and sync functions
        if asyncio.iscoroutinefunction(func):
            # Async function
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Emit counter before call
                await emitter.emit_counter(metric_name, 1.0, labels)
                return await func(*args, **kwargs)

            return cast(F, async_wrapper)
        else:
            # Sync function - shouldn't normally happen in async codebase
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Note: Can't await emit_counter in sync context
                # This is a limitation - decorator is primarily for async functions
                return func(*args, **kwargs)

            return cast(F, sync_wrapper)

    return decorator


def measure_duration(
    emitter: MetricsEmitter,
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> Callable[[F], F]:
    """Decorator to measure function execution duration.

    Args:
        emitter: MetricsEmitter instance
        metric_name: Name of the histogram metric
        labels: Static labels to attach to metric

    Returns:
        Decorator function

    Example:
        @measure_duration(emitter, "njord_processing_duration_seconds")
        async def process_event(self, event: TradeEvent) -> None:
            ...
    """

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError(f"measure_duration can only decorate callable, got {type(func)}")

        # Handle both async and sync functions
        if asyncio.iscoroutinefunction(func):
            # Async function
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    duration = time.perf_counter() - start_time
                    await emitter.emit_histogram(metric_name, duration, labels)

            return cast(F, async_wrapper)
        else:
            # Sync function
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Note: Can't await emit_histogram in sync context
                return func(*args, **kwargs)

            return cast(F, sync_wrapper)

    return decorator


def count_and_measure(
    emitter: MetricsEmitter,
    counter_name: str,
    histogram_name: str,
    labels: dict[str, str] | None = None,
) -> Callable[[F], F]:
    """Decorator to both count calls and measure duration.

    Args:
        emitter: MetricsEmitter instance
        counter_name: Name of the counter metric
        histogram_name: Name of the histogram metric
        labels: Static labels to attach to metrics

    Returns:
        Decorator function

    Example:
        @count_and_measure(
            emitter,
            "njord_requests_total",
            "njord_request_duration_seconds",
            {"service": "paper_trader"}
        )
        async def handle_request(self, req: Request) -> Response:
            ...
    """

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError(f"count_and_measure can only decorate callable, got {type(func)}")

        # Handle async functions
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Count the call
                await emitter.emit_counter(counter_name, 1.0, labels)

                # Measure duration
                start_time = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    duration = time.perf_counter() - start_time
                    await emitter.emit_histogram(histogram_name, duration, labels)

            return cast(F, async_wrapper)
        else:
            # Sync function
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return cast(F, sync_wrapper)

    return decorator
