from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

from apps.broker_binanceus import main as broker_main
from core.config import ApiKeysCfg, BinanceUSSecretsCfg, Config, SecretsCfg


def build_config(tmp_path: Path) -> Config:
    data = {
        "app": {"name": "test", "env": "test", "timezone": "UTC"},
        "logging": {"level": "INFO", "json": False, "journal_dir": str(tmp_path)},
        "redis": {
            "url": "redis://localhost:6379/0",
            "topics": {
                "trades": "md.trades.{symbol}",
                "book": "md.book.{symbol}",
                "ticker": "md.ticker.{symbol}",
                "intents": "intents.new",
                "risk": "risk.decision",
                "orders": "orders.accepted",
                "fills": "fills.new",
            },
        },
        "postgres": {"dsn": "postgresql://user:pass@localhost/db"},
        "exchange": {"venue": "test", "symbols": ["ATOMUSDT"], "ws_keepalive_sec": 15},
        "risk": {
            "per_order_usd_cap": 250.0,
            "daily_loss_usd_cap": 300.0,
            "orders_per_min_cap": 30,
            "kill_switch_file": str(tmp_path / "halt"),
            "kill_switch_key": "test:halt",
        },
        "paths": {
            "journal_dir": str(tmp_path),
            "experiments_dir": str(tmp_path / "experiments"),
        },
        "secrets": SecretsCfg(
            api_keys=ApiKeysCfg(binanceus=BinanceUSSecretsCfg(key="k", secret="s"))
        ),
    }
    return cast(Config, Config.model_validate(data))


def test_module_exports() -> None:
    assert hasattr(broker_main, "main")
    assert hasattr(broker_main, "run")


@pytest.mark.skipif(os.getenv("OFFLINE") == "1", reason="offline")
def test_binance_secrets_helper(tmp_path: Path) -> None:
    from apps.broker_binanceus.main import _binance_secrets

    cfg = build_config(tmp_path)
    key, secret = _binance_secrets(cfg)
    assert key == "k"
    assert secret == "s"

    cfg = cast(
        Config,
        Config.model_validate(
            {
                "app": {"name": "test", "env": "test", "timezone": "UTC"},
                "logging": {"level": "INFO", "json": False, "journal_dir": str(tmp_path)},
                "redis": {
                    "url": "redis://localhost:6379/0",
                    "topics": {
                        "trades": "md.trades.{symbol}",
                        "book": "md.book.{symbol}",
                        "ticker": "md.ticker.{symbol}",
                        "intents": "intents.new",
                        "risk": "risk.decision",
                        "orders": "orders.accepted",
                        "fills": "fills.new",
                    },
                },
                "postgres": {"dsn": "postgresql://user:pass@localhost/db"},
                "exchange": {"venue": "test", "symbols": ["ATOMUSDT"], "ws_keepalive_sec": 15},
                "risk": {
                    "per_order_usd_cap": 250.0,
                    "daily_loss_usd_cap": 300.0,
                    "orders_per_min_cap": 30,
                    "kill_switch_file": str(tmp_path / "halt"),
                    "kill_switch_key": "test:halt",
                },
                "paths": {
                    "journal_dir": str(tmp_path),
                    "experiments_dir": str(tmp_path / "experiments"),
                },
            }
        ),
    )
    key, secret = _binance_secrets(cfg)
    assert key is None
    assert secret is None

    # Import side effects exercised elsewhere; no connectivity here.
