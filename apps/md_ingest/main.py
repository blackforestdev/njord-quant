from __future__ import annotations

import argparse
import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any

from core.bus import Bus
from core.config import load_config
from core.journal import NdjsonJournal
from core.logging import setup_json_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Market data ingest daemon")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. ATOM/USDT")
    parser.add_argument("--venue", required=True, help="Exchange venue id supported by ccxt.pro")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    return parser


def _format_topic(template: str, symbol: str) -> str:
    try:
        return template.format(symbol=symbol)
    except KeyError:  # pragma: no cover - guard for unexpected templates
        return template


def _trade_event(trade: dict[str, Any], *, venue: str, symbol: str) -> dict[str, Any]:
    return {
        "type": "trade",
        "venue": venue,
        "symbol": symbol,
        "id": trade.get("id"),
        "price": trade.get("price"),
        "amount": trade.get("amount"),
        "side": trade.get("side"),
        "timestamp": trade.get("timestamp"),
        "raw": trade.get("info"),
    }


async def _stream_trades(
    venue: str, symbol: str, bus: Bus, journal: NdjsonJournal, topic: str
) -> None:
    try:
        import ccxtpro
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
        msg = "ccxt.pro is required for market data ingest"
        raise RuntimeError(msg) from exc

    try:
        exchange_cls = getattr(ccxtpro, venue)
    except AttributeError as exc:
        msg = f"Unknown ccxt.pro venue '{venue}'"
        raise RuntimeError(msg) from exc

    exchange = exchange_cls({"enableRateLimit": True})
    seen_keys: set[str] = set()
    recent_keys: deque[str] = deque()
    dedupe_limit = 512

    try:
        while True:
            trades = await exchange.watch_trades(symbol)
            if not trades:
                continue
            payloads = []
            for trade in trades:
                event = _trade_event(trade, venue=venue, symbol=symbol)
                trade_id = (
                    trade.get("id")
                    or f"{trade.get('timestamp')}:{trade.get('price')}:{trade.get('amount')}"
                )
                if trade_id in seen_keys:
                    continue
                seen_keys.add(trade_id)
                recent_keys.append(trade_id)
                if len(recent_keys) > dedupe_limit:
                    removed = recent_keys.popleft()
                    seen_keys.discard(removed)
                await bus.publish_json(topic, event)
                payloads.append(json.dumps(event, separators=(",", ":")))
            if payloads:
                journal.write_lines(payloads)
    except asyncio.CancelledError:  # pragma: no cover - allow graceful shutdown
        raise
    finally:
        await exchange.close()


async def run(symbol: str, venue: str, config_root: str) -> None:
    cfg = load_config(config_root)

    log_dir = Path(cfg.logging.journal_dir)
    logger = setup_json_logging(str(log_dir))

    journal_path = log_dir / f"md.trades.{symbol.replace('/', '')}.ndjson"
    journal = NdjsonJournal(journal_path)

    bus = Bus(cfg.redis.url)
    topic_template = cfg.redis.topics.trades
    topic = _format_topic(topic_template, symbol=symbol)

    logger.info(
        "md_ingest.start", venue=venue, symbol=symbol, topic=topic, journal=str(journal_path)
    )

    try:
        await _stream_trades(venue, symbol, bus, journal, topic)
    except KeyboardInterrupt:  # pragma: no cover - interactive run
        logger.info("md_ingest.stop", reason="keyboard-interrupt")
    finally:
        journal.close()
        await bus.close()


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        asyncio.run(run(args.symbol, args.venue, args.config_root))
    except RuntimeError as exc:  # bubble up friendly message
        parser.error(str(exc))


if __name__ == "__main__":  # pragma: no cover - manual execution path
    main()
