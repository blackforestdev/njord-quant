"""Unified journal reader returning pandas DataFrames or PyArrow tables."""

from __future__ import annotations

import gzip
import importlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, TextIO


class DataReaderError(RuntimeError):
    """Raised when journal data cannot be read."""


class DataReader:
    """Read market data, fills, and positions from local journals."""

    def __init__(
        self,
        journal_dir: Path | str,
        *,
        converters: Mapping[str, Callable[[list[dict[str, object]]], object]] | None = None,
    ) -> None:
        self._root = Path(journal_dir)
        if not self._root.exists():
            raise DataReaderError(f"Journal directory does not exist: {self._root}")
        self._converters: dict[str, Callable[[list[dict[str, object]]], object]] = dict(
            converters or {}
        )

    def read_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas",
    ) -> Any:
        safe_symbol = symbol.replace("/", "")
        pattern = f"ohlcv.{timeframe}.{safe_symbol}*.ndjson*"
        records = self._read_records(
            pattern,
            lambda row: start_ts <= _as_int(row.get("ts_open")) < end_ts,
        )
        return self._to_format(records, format)

    def read_trades(
        self,
        symbol: str,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas",
    ) -> Any:
        safe_symbol = symbol.replace("/", "")
        pattern = f"md.trades.{safe_symbol}*.ndjson*"

        def predicate(row: dict[str, object]) -> bool:
            ts_ms = _as_int(row.get("timestamp"))
            ts_ns = ts_ms * 1_000_000
            row["timestamp_ns"] = ts_ns
            return start_ts <= ts_ns < end_ts and str(row.get("symbol", "")) == symbol

        records = self._read_records(pattern, predicate)
        return self._to_format(records, format)

    def read_fills(
        self,
        strategy_id: str | None,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas",
    ) -> Any:
        pattern = "fills*.ndjson*"

        def predicate(row: dict[str, object]) -> bool:
            ts_ns = _as_int(row.get("ts_fill_ns"))
            if not (start_ts <= ts_ns < end_ts):
                return False
            if strategy_id is None:
                return True
            meta = row.get("meta") or {}
            if isinstance(meta, Mapping):
                return str(meta.get("strategy_id")) == strategy_id
            return False

        records = self._read_records(pattern, predicate)
        return self._to_format(records, format)

    def read_positions(
        self,
        portfolio_id: str,
        start_ts: int,
        end_ts: int,
        *,
        format: Literal["pandas", "arrow"] = "pandas",
    ) -> Any:
        pattern = "portfolio*.ndjson*"

        def predicate(row: dict[str, object]) -> bool:
            ts_ns = _as_int(row.get("ts_ns"))
            if not (start_ts <= ts_ns < end_ts):
                return False
            return str(row.get("portfolio_id", "")) == portfolio_id

        records = self._read_records(pattern, predicate)
        return self._to_format(records, format)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_records(
        self,
        pattern: str,
        predicate: Callable[[dict[str, object]], bool],
    ) -> list[dict[str, object]]:
        files = sorted(self._root.glob(pattern))
        if not files:
            return []

        records: list[dict[str, object]] = []
        for file_path in files:
            try:
                if file_path.suffix == ".gz":
                    with gzip.open(file_path, "rt", encoding="utf-8") as handle:
                        self._read_file(handle, predicate, records, file_path)
                else:
                    with open(file_path, encoding="utf-8") as handle:
                        self._read_file(handle, predicate, records, file_path)
            except OSError as exc:  # pragma: no cover
                raise DataReaderError(f"Failed reading {file_path}: {exc}") from exc
        return records

    def _read_file(
        self,
        handle: TextIO,
        predicate: Callable[[dict[str, object]], bool],
        records: list[dict[str, object]],
        file_path: Path,
    ) -> None:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise DataReaderError(f"Malformed JSON in {file_path}: {exc}") from exc
            if predicate(record):
                records.append(record)

    def _to_format(
        self,
        records: list[dict[str, object]],
        fmt: Literal["pandas", "arrow"],
    ) -> Any:
        if fmt in self._converters:
            return self._converters[fmt](records)
        if fmt == "pandas":
            pd = _import_optional("pandas", "pandas is required for format='pandas'")
            return pd.DataFrame(records)
        if fmt == "arrow":
            pa = _import_optional("pyarrow", "pyarrow is required for format='arrow'")
            return pa.Table.from_pylist(records)
        raise ValueError(f"Unsupported format '{fmt}'")


def _import_optional(module_name: str, message: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise DataReaderError(message) from exc


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:  # pragma: no cover - guarded by tests
            return default
    return default
