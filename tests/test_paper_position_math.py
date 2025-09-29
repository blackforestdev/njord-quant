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
async def test_position_math_partial_close(tmp_path: Path) -> None:
    bus = InMemoryBus()
    cfg = build_test_config(tmp_path, ["ATOM/USDT"])
    trader = PaperTrader(bus=bus, config=cfg, journal_dir=Path(cfg.logging.journal_dir))

    # Open long 4 @10
    trader.last_trade_price["ATOM/USDT"] = 10.0
    await trader.handle_order(
        {
            "intent_id": "o1",
            "venue": "test",
            "symbol": "ATOM/USDT",
            "side": "buy",
            "type": "market",
            "qty": 4.0,
            "limit_price": None,
            "ts_accepted_ns": 10,
        }
    )

    # Partial close 1 @11
    trader.last_trade_price["ATOM/USDT"] = 11.0
    await trader.handle_order(
        {
            "intent_id": "o2",
            "venue": "test",
            "symbol": "ATOM/USDT",
            "side": "sell",
            "type": "market",
            "qty": 1.0,
            "limit_price": None,
            "ts_accepted_ns": 11,
        }
    )

    # Reverse to net short 2 @9
    trader.last_trade_price["ATOM/USDT"] = 9.0
    await trader.handle_order(
        {
            "intent_id": "o3",
            "venue": "test",
            "symbol": "ATOM/USDT",
            "side": "sell",
            "type": "market",
            "qty": 5.0,
            "limit_price": None,
            "ts_accepted_ns": 12,
        }
    )

    state = trader.positions["ATOM/USDT"]
    assert state.qty == -2.0
    assert state.avg_price == 9.0
    assert pytest.approx(state.realized_pnl, rel=1e-9) == -2.0
