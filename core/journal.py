from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class NdjsonJournal:
    """Append-only NDJSON writer with explicit flushing semantics."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("a", encoding="utf-8")

    def write_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self._file.write(line.rstrip("\n") + "\n")
        self._file.flush()

    def rotate(self) -> None:  # pragma: no cover - rotation to be implemented later
        """Placeholder for future file rotation support."""

    def close(self) -> None:
        self._file.close()
