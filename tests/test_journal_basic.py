from __future__ import annotations

from pathlib import Path

from core.journal import NdjsonJournal


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_write_lines_appends(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.ndjson"

    journal = NdjsonJournal(journal_path)
    journal.write_lines(["first", "second"])
    journal.close()

    assert read_lines(journal_path) == ["first", "second"]
