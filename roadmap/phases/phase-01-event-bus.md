## Phase 1 — Event Bus & Market Data Ingest ✅

### Phase 1.0 — Redis Pub/Sub Bus ✅
**Status:** Complete
**Dependencies:** 0.4
**Task:** Async Redis wrapper for pub/sub

**API:**
```python
bus = Bus(redis_url)
await bus.publish_json(topic, payload)
async for msg in bus.subscribe(topic): ...
```

**Files:**
- `core/bus.py` (60 LOC)
- `tests/test_bus_pubsub.py` (requires Redis or fakeredis)

**Acceptance:** Round-trip message delivery verified

---

### Phase 1.1 — Market Data Contracts ✅
**Status:** Complete
**Dependencies:** 1.0
**Task:** Define event contracts in `core/contracts.py`

**Contracts:**
- `TradeEvent` (symbol, price, qty, side, ts)
- `BookEvent` (symbol, bids, asks, checksum)
- `TickerEvent` (symbol, last, bid, ask, volume)

**Files:**
- `core/contracts.py` (60 LOC, frozen dataclasses)
- `tests/test_contracts_basic.py`

**Acceptance:** Immutable, type-checked, serializable to dict

---

### Phase 1.2 — Market Data Ingest Daemon ✅
**Status:** Complete
**Dependencies:** 1.1
**Task:** Create `apps/md_ingest/main.py` using CCXT Pro

**Behavior:**
- `watch_trades(symbol)` → publish to `md.trades.{symbol}`
- Deduplicate by trade ID (rolling window of 512 IDs)
- Journal to `var/log/njord/md.trades.{symbol}.ndjson`
- Reconnect with exponential backoff on disconnect

**CLI:**
```bash
python -m apps.md_ingest --symbol ATOM/USDT --venue binanceus
```

**Files:**
- `apps/md_ingest/main.py` (120 LOC)
- `tests/test_md_ingest_dedupe.py`

**Acceptance:** Trades published without duplicates, journal replay matches

---
