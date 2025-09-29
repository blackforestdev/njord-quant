from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.bus import Bus
from core.config import Config, load_config
from core.journal import NdjsonJournal
from core.logging import setup_json_logging


class BusProto(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...


@dataclass
class PositionState:
    qty: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class PaperTrader:
    bus: BusProto
    config: Config
    journal_dir: Path
    positions: dict[str, PositionState] = field(default_factory=dict)
    last_trade_price: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._journals: dict[str, NdjsonJournal] = {}

    async def run(self) -> None:
        orders_topic = "orders.accepted"
        tasks = [asyncio.create_task(self._consume_orders(orders_topic))]
        trades_topic_template = self.config.redis.topics.trades
        for symbol in self.config.exchange.symbols:
            topic = trades_topic_template.format(symbol=symbol)
            tasks.append(asyncio.create_task(self._consume_trades(symbol, topic)))
        await asyncio.gather(*tasks)

    async def _consume_orders(self, topic: str) -> None:
        async for event in self.bus.subscribe(topic):
            await self.handle_order(event)

    async def _consume_trades(self, symbol: str, topic: str) -> None:
        async for trade in self.bus.subscribe(topic):
            price = trade.get("price")
            if price is None:
                continue
            self.last_trade_price[symbol] = float(price)

    async def handle_order(self, order: dict[str, Any]) -> None:
        symbol = order["symbol"]
        side = order["side"]
        order_type = order["type"]
        qty = float(order["qty"])
        limit_price = order.get("limit_price")
        last_price = self.last_trade_price.get(symbol)

        fill_price, meta = self._determine_fill_price(side, order_type, limit_price, last_price)
        self.last_trade_price[symbol] = fill_price

        self._apply_fill(symbol, side, qty, fill_price)

        fill_event = {
            "order_id": order.get("order_id", order["intent_id"]),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": fill_price,
            "fee": 0.0,
            "ts_fill_ns": time.time_ns(),
            "meta": meta,
        }
        await self.bus.publish_json("fills.new", fill_event)

        snapshot = self._snapshot(symbol)
        await self.bus.publish_json("positions.snapshot", snapshot)
        self._write_snapshot(symbol, snapshot)

    def _determine_fill_price(
        self,
        side: str,
        order_type: str,
        limit_price: float | None,
        last_price: float | None,
    ) -> tuple[float, dict[str, str]]:
        if order_type == "market":
            price = last_price if last_price is not None else (limit_price or 0.0)
            return float(price), {}

        # limit
        if limit_price is None:
            return float(last_price or 0.0), {"sim": "limit-forced"}

        if last_price is not None:
            crossed = (side == "buy" and last_price <= limit_price) or (
                side == "sell" and last_price >= limit_price
            )
            if crossed:
                return float(limit_price), {"sim": "limit-crossed"}

        return float(limit_price), {"sim": "limit-forced"}

    def _apply_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        state = self.positions.setdefault(symbol, PositionState())
        direction = 1.0 if side == "buy" else -1.0
        remaining = qty

        while remaining > 0:
            if state.qty == 0 or state.qty * direction > 0:
                new_qty = state.qty + direction * remaining
                total_cost = abs(state.qty) * state.avg_price + remaining * price
                state.qty = new_qty
                state.avg_price = total_cost / abs(new_qty) if new_qty else 0.0
                remaining = 0
            else:
                closing = min(abs(state.qty), remaining)
                if state.qty > 0:
                    state.realized_pnl += (price - state.avg_price) * closing
                else:
                    state.realized_pnl += (state.avg_price - price) * closing
                state.qty += direction * closing
                remaining -= closing
                if state.qty == 0:
                    state.avg_price = 0.0
                    if remaining > 0:
                        state.qty = direction * remaining
                        state.avg_price = price
                        remaining = 0

    def _snapshot(self, symbol: str) -> dict[str, Any]:
        state = self.positions[symbol]
        return {
            "symbol": symbol,
            "qty": state.qty,
            "avg_price": state.avg_price,
            "realized_pnl": state.realized_pnl,
            "ts_ns": time.time_ns(),
        }

    def _write_snapshot(self, symbol: str, snapshot: dict[str, Any]) -> None:
        journal = self._journals.get(symbol)
        if journal is None:
            filename = f"positions.{symbol.replace('/', '')}.ndjson"
            journal_path = self.journal_dir / filename
            journal = NdjsonJournal(journal_path)
            self._journals[symbol] = journal
        journal.write_lines([json.dumps(snapshot, separators=(",", ":"))])

    async def close(self) -> None:
        for journal in self._journals.values():
            journal.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper trader simulator")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    return parser


async def _run(config_root: str) -> None:
    cfg = load_config(config_root)
    log_dir = Path(cfg.logging.journal_dir)
    setup_json_logging(str(log_dir))
    bus = Bus(cfg.redis.url)
    trader = PaperTrader(bus=bus, config=cfg, journal_dir=log_dir)
    try:
        await trader.run()
    finally:
        await trader.close()
        await bus.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args.config_root))
    except KeyboardInterrupt:  # pragma: no cover - manual run
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
