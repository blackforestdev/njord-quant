from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

from apps.paper_trader.main import PaperTrader
from tests.utils import InMemoryBus, build_test_config

F = TypeVar("F", bound=Callable[..., None])


def typed(x: F) -> F:
    return x


@typed(pytest.mark.asyncio)
async def test_limit_buy_crosses_last_price(tmp_path: Path) -> None:
    bus = InMemoryBus()
    cfg = build_test_config(tmp_path, ["ATOM/USDT"])
    trader = PaperTrader(bus=bus, config=cfg, journal_dir=Path(cfg.logging.journal_dir))

    trader.last_trade_price["ATOM/USDT"] = 9.5

    order = {
        "intent_id": "order-2",
        "venue": "test",
        "symbol": "ATOM/USDT",
        "side": "buy",
        "type": "limit",
        "qty": 1.0,
        "limit_price": 10.0,
        "ts_accepted_ns": 2,
    }

    await trader.handle_order(order)

    fill = bus.published["fills.new"][-1]
    assert fill["price"] == 10.0
    assert fill["meta"]["sim"] == "limit-crossed"

    position = trader.positions["ATOM/USDT"]
    assert position.qty == 1.0
    assert position.avg_price == 10.0
