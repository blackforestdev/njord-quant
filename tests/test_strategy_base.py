from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from core.contracts import OrderIntent
from strategies.base import StrategyBase


class EchoStrategy(StrategyBase):
    strategy_id = "echo"

    def on_event(self, event: Any) -> Iterable[OrderIntent]:
        return (
            OrderIntent(
                id="intent-1",
                ts_local_ns=event["ts_local_ns"],
                strategy_id=self.strategy_id,
                symbol=event["symbol"],
                side="buy",
                type="market",
                qty=event["qty"],
                limit_price=None,
            ),
        )


def test_strategy_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        StrategyBase()  # type: ignore[abstract]


def test_strategy_subclass_generates_intent() -> None:
    strategy = EchoStrategy()
    event = {"symbol": "ATOM/USDT", "qty": 1.0, "ts_local_ns": 123}

    intents = list(strategy.on_event(event))

    assert len(intents) == 1
    intent = intents[0]
    assert intent.strategy_id == "echo"
    assert intent.symbol == "ATOM/USDT"
    assert intent.qty == 1.0
    assert intent.ts_local_ns == 123
