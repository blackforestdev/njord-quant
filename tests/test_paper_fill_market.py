from __future__ import annotations

import json
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
async def test_market_buy_updates_position(tmp_path: Path) -> None:
    bus = InMemoryBus()
    cfg = build_test_config(tmp_path, ["ATOM/USDT"])
    trader = PaperTrader(bus=bus, config=cfg, journal_dir=Path(cfg.logging.journal_dir))

    trader.last_trade_price["ATOM/USDT"] = 10.0

    order = {
        "intent_id": "order-1",
        "venue": "test",
        "symbol": "ATOM/USDT",
        "side": "buy",
        "type": "market",
        "qty": 2.0,
        "limit_price": None,
        "ts_accepted_ns": 1,
    }

    await trader.handle_order(order)

    position = trader.positions["ATOM/USDT"]
    assert position.qty == 2.0
    assert position.avg_price == 10.0

    fill = bus.published["fills.new"][-1]
    assert fill["price"] == 10.0
    assert fill["qty"] == 2.0

    journal_path = tmp_path / "positions.ATOMUSDT.ndjson"
    assert journal_path.exists()
    lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
    snapshot = json.loads(lines[-1])
    assert snapshot["qty"] == 2.0
