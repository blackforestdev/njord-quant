from __future__ import annotations

import json
import logging
from pathlib import Path

from core.logging import setup_json_logging


def read_last_line(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()
    return lines[-1].strip()


def test_json_logging_snapshot(tmp_path: Path) -> None:
    logger = setup_json_logging(str(tmp_path))

    logger.info("hello", k=1)

    for handler in logging.getLogger().handlers:
        handler.flush()

    log_path = tmp_path / "app.ndjson"
    payload = json.loads(read_last_line(log_path))

    assert payload["event"] == "hello"
    assert payload["k"] == 1
