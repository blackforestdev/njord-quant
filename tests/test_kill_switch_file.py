from __future__ import annotations

from pathlib import Path

from core.kill_switch import clear_file, file_tripped, trip_file


def test_file_kill_switch(tmp_path: Path) -> None:
    target = tmp_path / "flags" / "halt"

    assert file_tripped(str(target)) is False

    trip_file(str(target))
    assert file_tripped(str(target)) is True

    clear_file(str(target))
    assert file_tripped(str(target)) is False
