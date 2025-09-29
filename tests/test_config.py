from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.config import load_config


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_load_config_from_repo() -> None:
    cfg = load_config(repo_root())

    assert cfg.app.name == "njord"
    assert cfg.app.env == "dev"
    assert cfg.app.timezone == "UTC"
    assert cfg.logging.json is True
    assert cfg.redis.topics.trades == "md.trades.{symbol}"
    assert cfg.exchange.symbols == ["ATOM/USDT"]
    assert cfg.paths.journal_dir == Path("./data/journal")
    assert cfg.risk.per_order_usd_cap == 200.0
    assert cfg.risk.kill_switch_key == "njord:trading:halt"
    assert cfg.secrets.api_keys is None


def test_load_config_with_secrets(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    base_yaml = (repo_root() / "config" / "base.yaml").read_text(encoding="utf-8")
    (config_dir / "base.yaml").write_text(base_yaml, encoding="utf-8")

    secrets_data = {"api_keys": {"binanceus": {"key": "abc", "secret": "xyz"}}}
    (config_dir / "secrets.enc.yaml").write_text(yaml.safe_dump(secrets_data), encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.secrets.api_keys is not None
    assert cfg.secrets.api_keys.binanceus is not None
    assert cfg.secrets.api_keys.binanceus.key == "abc"


def test_load_config_missing_base(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        load_config(tmp_path)
