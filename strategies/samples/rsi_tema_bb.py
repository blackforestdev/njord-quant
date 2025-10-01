from __future__ import annotations

import statistics
import time
from collections import deque
from collections.abc import Iterable
from typing import Any

from core.contracts import OrderIntent
from strategies.base import StrategyBase

__all__ = ["RsiTemaBb"]


class RsiTemaBb(StrategyBase):
    """RSI + TEMA + Bollinger Bands strategy.

    Logic:
    - Buy: RSI oversold + price below lower band + TEMA rising
    - Sell: RSI overbought + price above upper band + TEMA falling
    """

    strategy_id = "rsi_tema_bb"

    def __init__(self) -> None:
        self._prices: deque[float] = deque()
        self._rsi_period = 14
        self._tema_period = 9
        self._bb_period = 20
        self._bb_std = 2.0
        self._rsi_oversold = 30.0
        self._rsi_overbought = 70.0
        self._qty = 1.0
        self._symbol = "ATOM/USDT"
        self._prev_tema: float | None = None

    def configure(self, params: dict[str, Any]) -> None:
        """Configure strategy parameters."""
        self._rsi_period = params.get("rsi_period", 14)
        self._tema_period = params.get("tema_period", 9)
        self._bb_period = params.get("bb_period", 20)
        self._bb_std = params.get("bb_std", 2.0)
        self._qty = params.get("qty", 1.0)
        self._symbol = params.get("symbol", "ATOM/USDT")
        self._rsi_oversold = params.get("rsi_oversold", 30.0)
        self._rsi_overbought = params.get("rsi_overbought", 70.0)

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        """Handle incoming trade event."""
        if not isinstance(event, dict):
            return []

        price = event.get("price")
        symbol = event.get("symbol", self._symbol)

        if price is None:
            return []

        self._prices.append(price)

        # Need sufficient data
        max_period = max(self._rsi_period, self._tema_period, self._bb_period)
        if len(self._prices) < max_period + 1:
            return []

        # Compute indicators
        rsi = self._compute_rsi()
        tema = self._compute_tema()
        bb_upper, bb_lower = self._compute_bollinger_bands()

        if rsi is None or tema is None or bb_upper is None or bb_lower is None:
            self._prev_tema = tema
            return []

        # Check signals
        tema_rising = self._prev_tema is not None and tema > self._prev_tema
        tema_falling = self._prev_tema is not None and tema < self._prev_tema

        self._prev_tema = tema

        # Buy signal: RSI oversold + price below lower band + TEMA rising
        if rsi < self._rsi_oversold and price < bb_lower and tema_rising:
            return [
                OrderIntent(
                    id=f"rsi_tema_bb_buy_{int(time.time_ns())}",
                    ts_local_ns=event.get("ts_local_ns", int(time.time_ns())),
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    side="buy",
                    type="market",
                    qty=self._qty,
                    limit_price=None,
                )
            ]

        # Sell signal: RSI overbought + price above upper band + TEMA falling
        if rsi > self._rsi_overbought and price > bb_upper and tema_falling:
            return [
                OrderIntent(
                    id=f"rsi_tema_bb_sell_{int(time.time_ns())}",
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

    def _compute_rsi(self) -> float | None:
        """Compute RSI indicator."""
        if len(self._prices) < self._rsi_period + 1:
            return None

        prices = list(self._prices)[-(self._rsi_period + 1) :]
        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))

        avg_gain = sum(gains) / len(gains) if gains else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    def _compute_tema(self) -> float | None:
        """Compute TEMA (Triple Exponential Moving Average)."""
        if len(self._prices) < self._tema_period:
            return None

        prices = list(self._prices)[-self._tema_period :]
        ema1 = self._ema(prices, self._tema_period)
        ema2 = self._ema([ema1] * len(prices), self._tema_period)
        ema3 = self._ema([ema2] * len(prices), self._tema_period)

        tema = 3 * ema1 - 3 * ema2 + ema3

        return tema

    def _compute_bollinger_bands(self) -> tuple[float | None, float | None]:
        """Compute Bollinger Bands (upper, lower)."""
        if len(self._prices) < self._bb_period:
            return None, None

        prices = list(self._prices)[-self._bb_period :]
        sma = statistics.mean(prices)
        std = statistics.stdev(prices)

        upper = sma + self._bb_std * std
        lower = sma - self._bb_std * std

        return upper, lower

    def _ema(self, values: list[float], period: int) -> float:
        """Compute exponential moving average."""
        if not values:
            return 0.0

        multiplier = 2.0 / (period + 1)
        ema = values[0]

        for value in values[1:]:
            ema = (value - ema) * multiplier + ema

        return ema
