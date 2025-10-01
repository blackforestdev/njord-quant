from __future__ import annotations

import statistics
import time
from collections import deque
from collections.abc import Iterable
from typing import Any

from core.contracts import OrderIntent
from strategies.base import StrategyBase

__all__ = ["TrendlineBreak"]


class TrendlineBreak(StrategyBase):
    """Trendline breakout strategy using linear regression.

    Logic:
    - Maintain rolling window of last N prices
    - Compute linear regression trendline
    - If current price breaks above trendline by threshold → buy signal
    - If breaks below → sell signal
    """

    strategy_id = "trendline_break"

    def __init__(self) -> None:
        self._price_window: deque[float] = deque()
        self._lookback_periods = 20
        self._breakout_threshold = 0.02
        self._qty = 1.0
        self._symbol = "ATOM/USDT"

    def configure(self, params: dict[str, Any]) -> None:
        """Configure strategy parameters."""
        self._lookback_periods = params.get("lookback_periods", 20)
        self._breakout_threshold = params.get("breakout_threshold", 0.02)
        self._qty = params.get("qty", 1.0)
        self._symbol = params.get("symbol", "ATOM/USDT")

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        """Handle incoming trade event."""
        # Extract price from event
        if not isinstance(event, dict):
            return []

        price = event.get("price")
        symbol = event.get("symbol", self._symbol)

        if price is None:
            return []

        # Need at least 3 points for regression (before adding current price)
        if len(self._price_window) < 3:
            self._price_window.append(price)
            return []

        # Compute trendline value at NEXT position (before adding current price)
        trendline_value = self._compute_trendline_next()

        if trendline_value is None:
            self._price_window.append(price)
            if len(self._price_window) > self._lookback_periods:
                self._price_window.popleft()
            return []

        # Check for breakout against expected trendline value
        breakout_ratio = (price - trendline_value) / trendline_value

        # Add current price to window after computing trendline
        self._price_window.append(price)
        if len(self._price_window) > self._lookback_periods:
            self._price_window.popleft()

        if breakout_ratio > self._breakout_threshold:
            # Breakout above → buy signal
            return [
                OrderIntent(
                    id=f"trendline_buy_{int(time.time_ns())}",
                    ts_local_ns=event.get("ts_local_ns", int(time.time_ns())),
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    side="buy",
                    type="market",
                    qty=self._qty,
                    limit_price=None,
                )
            ]
        elif breakout_ratio < -self._breakout_threshold:
            # Breakout below → sell signal
            return [
                OrderIntent(
                    id=f"trendline_sell_{int(time.time_ns())}",
                    ts_local_ns=event.get("ts_local_ns", int(time.time_ns())),
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    side="sell",
                    type="market",
                    qty=self._qty,
                    limit_price=None,
                )
            ]

        return []

    def _compute_trendline_next(self) -> float | None:
        """Compute linear regression trendline value at NEXT position."""
        if len(self._price_window) < 2:
            return None

        prices = list(self._price_window)
        n = len(prices)

        # X values are 0, 1, 2, ..., n-1
        x_values = list(range(n))

        try:
            # Compute linear regression: y = slope * x + intercept
            slope, intercept = self._linear_regression(x_values, prices)

            # Return trendline value at the NEXT position (n, not n-1)
            trendline_value = slope * n + intercept

            return trendline_value
        except Exception:
            return None

    def _linear_regression(self, x: list[int], y: list[float]) -> tuple[float, float]:
        """Compute linear regression slope and intercept using stdlib."""
        n = len(x)

        # Calculate means
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)

        # Calculate slope
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            raise ValueError("Cannot compute regression: zero variance in x")

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        return slope, intercept
