"""Unit tests for the research data reader."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from research.data_reader import DataReader, DataReaderError


class StubDataFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.iloc = _ILoc(rows)

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def empty(self) -> bool:
        return not self._rows

    def __getitem__(self, key: str) -> list[object]:
        return [row.get(key) for row in self._rows]


class _ILoc:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def __getitem__(self, index: int) -> dict[str, object]:
        return self._rows[index]


class StubArrowTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.num_rows = len(rows)

    def column(self, name: str) -> list[object]:
        return [row.get(name) for row in self._rows]


def _write_ndjson(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _write_ndjson_gz(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def test_read_ohlcv_pandas(tmp_path: Path) -> None:
    journal_dir = tmp_path / "journals"
    _write_ndjson(
        journal_dir / "ohlcv.1m.ATOMUSDT.20250101.ndjson",
        [
            {
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "ts_open": 0,
                "ts_close": 60_000_000_000,
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 100.0,
            },
            {
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "ts_open": 60_000_000_000,
                "ts_close": 120_000_000_000,
                "open": 10.5,
                "high": 10.8,
                "low": 10.2,
                "close": 10.6,
                "volume": 80.0,
            },
        ],
    )
    _write_ndjson_gz(
        journal_dir / "ohlcv.1m.ATOMUSDT.20250102.ndjson.gz",
        [
            {
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "ts_open": 120_000_000_000,
                "ts_close": 180_000_000_000,
                "open": 10.6,
                "high": 10.9,
                "low": 10.3,
                "close": 10.7,
                "volume": 120.0,
            }
        ],
    )

    converters = {
        "pandas": StubDataFrame,
        "arrow": StubArrowTable,
    }
    reader = DataReader(journal_dir, converters=converters)
    df = reader.read_ohlcv(
        symbol="ATOM/USDT",
        timeframe="1m",
        start_ts=0,
        end_ts=150_000_000_000,
        format="pandas",
    )

    assert isinstance(df, StubDataFrame)
    assert len(df) == 3
    first_row = df.iloc[0]
    assert first_row["open"] == 10.0


def test_read_trades_arrow(tmp_path: Path) -> None:
    journal_dir = tmp_path / "journals"
    _write_ndjson(
        journal_dir / "md.trades.ATOMUSDT.ndjson",
        [
            {
                "type": "trade",
                "symbol": "ATOM/USDT",
                "price": 10.0,
                "amount": 1.0,
                "timestamp": 1_000,
            },
            {
                "type": "trade",
                "symbol": "ATOM/USDT",
                "price": 11.0,
                "amount": 2.0,
                "timestamp": 2_000,
            },
        ],
    )

    converters = {
        "pandas": StubDataFrame,
        "arrow": StubArrowTable,
    }
    reader = DataReader(journal_dir, converters=converters)
    table = reader.read_trades(
        symbol="ATOM/USDT",
        start_ts=0,
        end_ts=3_000_000_000,
        format="arrow",
    )

    assert isinstance(table, StubArrowTable)
    assert table.num_rows == 2
    assert table.column("timestamp_ns")[0] == 1_000_000_000


def test_read_fills_filters_strategy(tmp_path: Path) -> None:
    journal_dir = tmp_path / "journals"
    _write_ndjson(
        journal_dir / "fills.ndjson",
        [
            {
                "order_id": "1",
                "symbol": "ATOM/USDT",
                "side": "buy",
                "qty": 1.0,
                "price": 10.0,
                "ts_fill_ns": 1_500,
                "meta": {"strategy_id": "alpha"},
            },
            {
                "order_id": "2",
                "symbol": "ATOM/USDT",
                "side": "sell",
                "qty": 1.5,
                "price": 10.5,
                "ts_fill_ns": 2_500,
                "meta": {"strategy_id": "beta"},
            },
        ],
    )

    converters = {
        "pandas": StubDataFrame,
        "arrow": StubArrowTable,
    }
    reader = DataReader(journal_dir, converters=converters)
    df = reader.read_fills(
        strategy_id="alpha",
        start_ts=0,
        end_ts=5_000,
        format="pandas",
    )

    assert isinstance(df, StubDataFrame)
    assert len(df) == 1
    assert df.iloc[0]["order_id"] == "1"


def test_read_positions_returns_empty_when_missing(tmp_path: Path) -> None:
    converters = {
        "pandas": StubDataFrame,
        "arrow": StubArrowTable,
    }
    reader = DataReader(tmp_path, converters=converters)
    df = reader.read_positions(
        portfolio_id="missing",
        start_ts=0,
        end_ts=10,
        format="pandas",
    )
    assert isinstance(df, StubDataFrame)
    assert df.empty


def test_data_reader_missing_dir() -> None:
    with pytest.raises(DataReaderError):
        DataReader(Path("/nonexistent/path"))
