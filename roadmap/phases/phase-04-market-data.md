## Phase 4 — Market Data Storage ✅

### Phase 4.1 — OHLCV Bar Dataclass ✅
**Status:** Complete
**Dependencies:** 1.2 (Market Data Ingest)
**Task:** Define OHLCV bar contract

**API:**
```python
@dataclass(frozen=True)
class OHLCVBar:
    symbol: str
    timeframe: str  # "1m", "5m", "1h"
    ts_open: int    # epoch ns
    ts_close: int
    open: float
    high: float
    low: float
    close: float
    volume: float
```

**Files:**
- core/contracts.py (append ~30 LOC)
- tests/test_ohlcv_contract.py

**Acceptance:**
- Immutable dataclass (frozen=True)
- All fields typed correctly
- Serializable to/from dict
- Test verifies immutability
- `make fmt lint type test` green

---

### Phase 4.2 — Trade-to-OHLCV Aggregator ✅
**Status:** Complete
**Dependencies:** 4.1 (OHLCV Bar Dataclass)
**Task:** Aggregate trades into OHLCV bars

**Behavior:**
- Subscribe to md.trades.{symbol} topic
- Buffer trades in memory per timeframe
- Emit complete bars when time window closes
- Publish to md.ohlcv.{timeframe}.{symbol} topic
- Handle gaps (no trades) by repeating last close

**Files:**
- apps/ohlcv_aggregator/main.py (150 LOC)
- tests/test_ohlcv_aggregator.py

**Acceptance:**
- Deterministic bar creation verified
- Gap handling tested (no trades → repeat close)
- Edge cases covered (single trade, midnight boundary)
- Bars published to correct Redis topics
- `make fmt lint type test` green

---

### Phase 4.3 — Multi-Timeframe Support ✅
**Status:** Complete
**Dependencies:** 4.2
**Task:** Support multiple concurrent timeframes

**Behavior:**
- Single aggregator instance handles ["1m", "5m", "15m", "1h"]
- Each timeframe has independent buffer
- 5m/15m/1h bars derived from 1m (not raw trades)
- Aligned to wall-clock boundaries (e.g., 1h bar at :00)

**Files:**
- apps/ohlcv_aggregator/main.py (append ~80 LOC)
- tests/test_multi_timeframe.py

**Acceptance:**
- All timeframes align to wall-clock boundaries
- No drift detected across 24h simulation
- 5m/15m/1h bars correctly derived from 1m
- Test includes concurrent multi-timeframe aggregation
- `make fmt lint type test` green

---

### Phase 4.4 — OHLCV Persistence ✅
**Status:** Complete
**Dependencies:** 4.3
**Task:** Journal OHLCV bars to disk

**Behavior:**
- Write bars to var/log/njord/ohlcv.{timeframe}.{symbol}.ndjson
- One line per bar (JSON serialized)
- Flush after each bar
- Separate journal per symbol+timeframe

**Files:**
- apps/ohlcv_aggregator/main.py (append ~40 LOC)
- tests/test_ohlcv_persistence.py

**Acceptance:**
- Journals written to correct paths
- NDJSON format parseable
- Replay matches original bars exactly
- Flush after each bar verified
- `make fmt lint type test` green

---

### Phase 4.5 — Gzip Compression Service ✅
**Status:** Complete
**Dependencies:** 4.4
**Task:** Compress old OHLCV journals

**Behavior:**
- Scan var/log/njord/ for .ndjson files older than 24h
- Compress with gzip (level 6)
- Rename: file.ndjson → file.YYYYMMDD.ndjson.gz
- Remove original uncompressed file
- Run as cron job or systemd timer

**Files:**
- scripts/compress_journals.py (80 LOC)
- tests/test_compression.py

**Acceptance:**
- [x] Compressed files readable with gzip
- [x] Original content preserved bit-for-bit
- [x] Files older than 24h correctly identified
- [x] Compression ratio >50% on test data
- [x] `make fmt lint type test` green

---

### Phase 4.6 — Rotation Policy ✅
**Status:** Complete
**Dependencies:** 4.5
**Task:** Rotate journals by date/size

**Behavior:**
- Daily rotation: start new journal at midnight UTC
- Size rotation: if journal exceeds 100MB, rotate immediately
- Naming: ohlcv.1m.ATOMUSDT.20250930.ndjson
- Compress rotated files automatically

**Files:**
- apps/ohlcv_aggregator/rotator.py (60 LOC)
- tests/test_rotation.py

**Acceptance:**
- [x] Daily rotation triggers at midnight UTC
- [x] Size rotation triggers at 100MB threshold
- [x] No data loss during rotation
- [x] Naming convention followed exactly
- [x] `make fmt lint type test` green

---

### Phase 4.7 — Journal Reader API ✅
**Status:** Complete
**Dependencies:** 4.6
**Task:** Read OHLCV journals for replay
**API:**
```python
class JournalReader:
    def __init__(self, path: Path): ...

    def read_bars(
        self,
        symbol: str,
        timeframe: str,
        start: int,  # epoch ns
        end: int
    ) -> Iterator[OHLCVBar]: ...
```

**Behavior:**
- Handle both compressed (.gz) and uncompressed files
- Filter by time range
- Parse NDJSON lines into OHLCVBar objects
- Raise error on malformed lines

**Files:**
- core/journal_reader.py (100 LOC)
- tests/test_journal_reader.py

**Acceptance:**
- [x] Reads both .ndjson and .ndjson.gz files
- [x] Time range filtering accurate to nanosecond
- [x] Malformed lines raise clear errors
- [x] Iterator pattern works for large files
- [x] `make fmt lint type test` green

---

### Phase 4.8 — Event Stream Replay ✅
**Status:** Complete
**Dependencies:** 4.7
**Task:** Replay historical OHLCV bars
**Behavior:**
- Load bars from journals
- Emit to Redis bus at controlled speed
- Publish to same topics as live aggregator
- Support speed multiplier (1x, 10x, 100x, max)
- Replay multiple symbols concurrently

**Files:**
- apps/replay_engine/main.py (120 LOC)
- tests/test_replay_engine.py

**Acceptance:**
- [x] Replay produces identical event sequences
- [x] Speed control verified (1x, 10x, 100x)
- [x] Multiple symbols replay concurrently without interference
- [x] Deterministic across multiple runs
- [x] `make fmt lint type test` green

---

### Phase 4.9 — Replay CLI ✅
**Status:** Complete
**Dependencies:** 4.8
**Task:** Command-line interface for replay

**CLI:**
```bash
python -m apps.replay_engine \
    --symbol ATOM/USDT \
    --timeframe 1m \
    --start 2025-09-01T00:00:00Z \
    --end 2025-09-30T23:59:59Z \
    --speed 10x
```

**Files:**
- apps/replay_engine/main.py (append ~50 LOC)
- tests/test_replay_cli.py

**Acceptance:**
- [x] All CLI arguments parsed correctly
- [x] Date/time parsing handles ISO 8601
- [x] Invalid args produce helpful error messages
- [x] CLI help text complete and accurate
- [x] `make fmt lint type test` green

---

**Phase 4 Acceptance Criteria:**
- [x] All 9 tasks completed
- [x] make fmt lint type test green
- [x] OHLCV bars persist and compress correctly
- [x] Replay deterministic across all timeframes
- [x] Journals rotate without data loss

---
