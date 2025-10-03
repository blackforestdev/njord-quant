"""Sync/async adapters for execution layer.

This module provides wrappers to bridge async executors with sync contexts
(e.g., backtesting engine) and vice versa.

WARNING: SyncExecutionWrapper uses asyncio.run() which creates a new event loop.
This is ONLY safe in pure sync contexts. It will FAIL if called from within
an existing event loop (e.g., from async services like risk_engine, broker).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from core.contracts import OrderIntent
from execution.base import BaseExecutor

if TYPE_CHECKING:
    # ExecutionAlgorithm will be defined in Phase 8.1
    ExecutionAlgorithm = Any


class SyncExecutionWrapper:
    """Wrap async executor for sync contexts (backtest).

    WARNING: Uses asyncio.run() which creates a new event loop.
    - Safe in pure sync contexts (backtest engine)
    - FAILS if called from within an existing event loop
    - Do NOT use in async services (risk_engine, broker, etc.)

    Example (Backtest - Safe):
        >>> executor = TWAPExecutor(strategy_id="strat_1")
        >>> sync_wrapper = SyncExecutionWrapper(executor)
        >>> intents = sync_wrapper.plan_execution_sync(algo)

    Example (Async Service - UNSAFE):
        >>> # DO NOT DO THIS - will raise RuntimeError
        >>> async def some_service():
        ...     wrapper = SyncExecutionWrapper(executor)
        ...     intents = wrapper.plan_execution_sync(algo)  # FAILS!
    """

    def __init__(self, async_executor: BaseExecutor) -> None:
        """Initialize wrapper.

        Args:
            async_executor: Async executor to wrap
        """
        self.async_executor = async_executor

    def plan_execution_sync(self, algo: ExecutionAlgorithm) -> list[OrderIntent]:
        """Synchronous wrapper for async executor.

        Runs the async plan_execution() method in a new event loop.

        Args:
            algo: Execution algorithm configuration

        Returns:
            List of OrderIntents

        Raises:
            RuntimeError: If called from within an existing event loop

        Note:
            Only use in pure sync contexts (backtest engine).
            Do NOT use in async services.
        """
        try:
            # Check if we're already in an event loop
            asyncio.get_running_loop()
            raise RuntimeError(
                "SyncExecutionWrapper.plan_execution_sync() cannot be called "
                "from within an existing event loop. Use the async executor "
                "directly in async contexts."
            )
        except RuntimeError as e:
            # If get_running_loop() raises, we're NOT in an event loop (safe)
            if "no running event loop" not in str(e).lower():
                # Re-raise if it's the error we threw above
                raise

        # Safe to create new event loop
        return asyncio.run(self.async_executor.plan_execution(algo))
