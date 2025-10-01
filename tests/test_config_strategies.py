from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]


def test_strategies_yaml_exists() -> None:
    """Test that strategies.yaml exists in config directory."""
    config_path = Path("config/strategies.yaml")
    assert config_path.exists()


def test_strategies_yaml_parses() -> None:
    """Test that strategies.yaml is valid YAML."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config is not None
    assert "strategies" in config


def test_strategies_have_required_fields() -> None:
    """Test that each strategy has required fields."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]
    assert len(strategies) > 0

    required_fields = {"id", "class", "symbols", "events", "params"}

    for strategy in strategies:
        for field in required_fields:
            assert field in strategy, f"Strategy {strategy.get('id')} missing field: {field}"


def test_strategy_ids_are_unique() -> None:
    """Test that strategy IDs are unique."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]
    ids = [s["id"] for s in strategies]

    assert len(ids) == len(set(ids)), "Strategy IDs are not unique"


def test_symbols_are_lists() -> None:
    """Test that symbols field is a list."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]

    for strategy in strategies:
        assert isinstance(strategy["symbols"], list)
        assert len(strategy["symbols"]) > 0


def test_events_are_lists() -> None:
    """Test that events field is a list."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]

    for strategy in strategies:
        assert isinstance(strategy["events"], list)
        assert len(strategy["events"]) > 0


def test_params_are_dicts() -> None:
    """Test that params field is a dict."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]

    for strategy in strategies:
        assert isinstance(strategy["params"], dict)


def test_trendline_break_config() -> None:
    """Test trendline_break_v1 strategy configuration."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]
    trendline = next(s for s in strategies if s["id"] == "trendline_break_v1")

    assert trendline["class"] == "strategies.samples.trendline_break.TrendlineBreak"
    assert trendline["enabled"] is True
    assert "ATOM/USDT" in trendline["symbols"]
    assert "md.trades.*" in trendline["events"]
    assert trendline["params"]["lookback_periods"] == 20
    assert trendline["params"]["breakout_threshold"] == 0.02


def test_rsi_tema_bb_config() -> None:
    """Test rsi_tema_bb_v1 strategy configuration."""
    config_path = Path("config/strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    strategies = config["strategies"]
    rsi_tema = next(s for s in strategies if s["id"] == "rsi_tema_bb_v1")

    assert rsi_tema["class"] == "strategies.samples.rsi_tema_bb.RsiTemaBb"
    assert rsi_tema["enabled"] is False
    assert "ATOM/USDT" in rsi_tema["symbols"]
    assert "md.trades.*" in rsi_tema["events"]
    assert rsi_tema["params"]["rsi_period"] == 14
    assert rsi_tema["params"]["tema_period"] == 9
    assert rsi_tema["params"]["bb_period"] == 20
    assert rsi_tema["params"]["bb_std"] == 2.0
