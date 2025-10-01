from __future__ import annotations

import json

import pytest

from backtest.contracts import BacktestConfig, BacktestResult


def test_backtest_config_creation() -> None:
    """Test creating a backtest configuration."""
    config = BacktestConfig(
        symbol="ATOM/USDT",
        strategy_id="trendline_break_v1",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        commission_rate=0.001,
        slippage_bps=5.0,
    )

    assert config.symbol == "ATOM/USDT"
    assert config.strategy_id == "trendline_break_v1"
    assert config.start_ts == 1000000000_000_000_000
    assert config.end_ts == 2000000000_000_000_000
    assert config.initial_capital == 10000.0
    assert config.commission_rate == 0.001
    assert config.slippage_bps == 5.0


def test_backtest_config_immutable() -> None:
    """Test that BacktestConfig is immutable."""
    config = BacktestConfig(
        symbol="ATOM/USDT",
        strategy_id="test",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        commission_rate=0.001,
        slippage_bps=5.0,
    )

    with pytest.raises(AttributeError):
        config.symbol = "BTC/USDT"  # type: ignore[misc]


def test_backtest_config_validation_start_before_end() -> None:
    """Test that start_ts must be before end_ts."""
    with pytest.raises(ValueError, match="start_ts must be before end_ts"):
        BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=2000000000_000_000_000,
            end_ts=1000000000_000_000_000,  # Before start!
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
        )


def test_backtest_config_validation_positive_capital() -> None:
    """Test that initial_capital must be positive."""
    with pytest.raises(ValueError, match="initial_capital must be positive"):
        BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=1000000000_000_000_000,
            end_ts=2000000000_000_000_000,
            initial_capital=0.0,  # Invalid!
            commission_rate=0.001,
            slippage_bps=5.0,
        )


def test_backtest_config_validation_non_negative_commission() -> None:
    """Test that commission_rate cannot be negative."""
    with pytest.raises(ValueError, match="commission_rate cannot be negative"):
        BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=1000000000_000_000_000,
            end_ts=2000000000_000_000_000,
            initial_capital=10000.0,
            commission_rate=-0.001,  # Invalid!
            slippage_bps=5.0,
        )


def test_backtest_config_validation_non_negative_slippage() -> None:
    """Test that slippage_bps cannot be negative."""
    with pytest.raises(ValueError, match="slippage_bps cannot be negative"):
        BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=1000000000_000_000_000,
            end_ts=2000000000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=-5.0,  # Invalid!
        )


def test_backtest_result_creation() -> None:
    """Test creating a backtest result."""
    equity_curve = [
        (1000000000_000_000_000, 10000.0),
        (1100000000_000_000_000, 10500.0),
        (1200000000_000_000_000, 11000.0),
    ]

    result = BacktestResult(
        strategy_id="trendline_break_v1",
        symbol="ATOM/USDT",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        final_capital=11000.0,
        total_return_pct=10.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=5.0,
        num_trades=10,
        win_rate=0.6,
        profit_factor=2.0,
        equity_curve=equity_curve,
    )

    assert result.strategy_id == "trendline_break_v1"
    assert result.symbol == "ATOM/USDT"
    assert result.final_capital == 11000.0
    assert result.total_return_pct == 10.0
    assert result.sharpe_ratio == 1.5
    assert result.max_drawdown_pct == 5.0
    assert result.num_trades == 10
    assert result.win_rate == 0.6
    assert result.profit_factor == 2.0
    assert len(result.equity_curve) == 3


def test_backtest_result_immutable() -> None:
    """Test that BacktestResult is immutable."""
    result = BacktestResult(
        strategy_id="test",
        symbol="ATOM/USDT",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        final_capital=11000.0,
        total_return_pct=10.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=5.0,
        num_trades=10,
        win_rate=0.6,
        profit_factor=2.0,
        equity_curve=[],
    )

    with pytest.raises(AttributeError):
        result.final_capital = 12000.0  # type: ignore[misc]


def test_backtest_result_to_dict() -> None:
    """Test converting result to dictionary."""
    equity_curve = [
        (1000000000_000_000_000, 10000.0),
        (1100000000_000_000_000, 10500.0),
    ]

    result = BacktestResult(
        strategy_id="test",
        symbol="ATOM/USDT",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        final_capital=10500.0,
        total_return_pct=5.0,
        sharpe_ratio=1.2,
        max_drawdown_pct=2.0,
        num_trades=5,
        win_rate=0.8,
        profit_factor=3.0,
        equity_curve=equity_curve,
    )

    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["strategy_id"] == "test"
    assert result_dict["final_capital"] == 10500.0
    assert result_dict["equity_curve"] == equity_curve


def test_backtest_result_to_json() -> None:
    """Test JSON serialization of result."""
    equity_curve = [
        (1000000000_000_000_000, 10000.0),
        (1100000000_000_000_000, 10500.0),
    ]

    result = BacktestResult(
        strategy_id="test",
        symbol="ATOM/USDT",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        final_capital=10500.0,
        total_return_pct=5.0,
        sharpe_ratio=1.2,
        max_drawdown_pct=2.0,
        num_trades=5,
        win_rate=0.8,
        profit_factor=3.0,
        equity_curve=equity_curve,
    )

    json_str = result.to_json()

    assert isinstance(json_str, str)

    # Verify it's valid JSON
    parsed = json.loads(json_str)
    assert parsed["strategy_id"] == "test"
    assert parsed["final_capital"] == 10500.0


def test_backtest_result_from_dict() -> None:
    """Test creating result from dictionary."""
    data = {
        "strategy_id": "test",
        "symbol": "ATOM/USDT",
        "start_ts": 1000000000_000_000_000,
        "end_ts": 2000000000_000_000_000,
        "initial_capital": 10000.0,
        "final_capital": 10500.0,
        "total_return_pct": 5.0,
        "sharpe_ratio": 1.2,
        "max_drawdown_pct": 2.0,
        "num_trades": 5,
        "win_rate": 0.8,
        "profit_factor": 3.0,
        "equity_curve": [
            [1000000000_000_000_000, 10000.0],
            [1100000000_000_000_000, 10500.0],
        ],
    }

    result = BacktestResult.from_dict(data)

    assert result.strategy_id == "test"
    assert result.final_capital == 10500.0
    assert len(result.equity_curve) == 2
    assert result.equity_curve[0] == (1000000000_000_000_000, 10000.0)


def test_backtest_result_from_json() -> None:
    """Test deserializing result from JSON."""
    json_str = """
    {
        "strategy_id": "test",
        "symbol": "ATOM/USDT",
        "start_ts": 1000000000000000000,
        "end_ts": 2000000000000000000,
        "initial_capital": 10000.0,
        "final_capital": 10500.0,
        "total_return_pct": 5.0,
        "sharpe_ratio": 1.2,
        "max_drawdown_pct": 2.0,
        "num_trades": 5,
        "win_rate": 0.8,
        "profit_factor": 3.0,
        "equity_curve": [
            [1000000000000000000, 10000.0],
            [1100000000000000000, 10500.0]
        ]
    }
    """

    result = BacktestResult.from_json(json_str)

    assert result.strategy_id == "test"
    assert result.final_capital == 10500.0
    assert len(result.equity_curve) == 2


def test_backtest_result_json_roundtrip() -> None:
    """Test that result survives JSON serialization roundtrip."""
    equity_curve = [
        (1000000000_000_000_000, 10000.0),
        (1100000000_000_000_000, 10500.0),
        (1200000000_000_000_000, 11000.0),
    ]

    original = BacktestResult(
        strategy_id="roundtrip_test",
        symbol="ATOM/USDT",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        final_capital=11000.0,
        total_return_pct=10.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=5.0,
        num_trades=10,
        win_rate=0.6,
        profit_factor=2.0,
        equity_curve=equity_curve,
    )

    # Serialize and deserialize
    json_str = original.to_json()
    restored = BacktestResult.from_json(json_str)

    # Verify all fields match
    assert restored.strategy_id == original.strategy_id
    assert restored.symbol == original.symbol
    assert restored.start_ts == original.start_ts
    assert restored.end_ts == original.end_ts
    assert restored.initial_capital == original.initial_capital
    assert restored.final_capital == original.final_capital
    assert restored.total_return_pct == original.total_return_pct
    assert restored.sharpe_ratio == original.sharpe_ratio
    assert restored.max_drawdown_pct == original.max_drawdown_pct
    assert restored.num_trades == original.num_trades
    assert restored.win_rate == original.win_rate
    assert restored.profit_factor == original.profit_factor
    assert restored.equity_curve == original.equity_curve


def test_equity_curve_empty() -> None:
    """Test result with empty equity curve."""
    result = BacktestResult(
        strategy_id="test",
        symbol="ATOM/USDT",
        start_ts=1000000000_000_000_000,
        end_ts=2000000000_000_000_000,
        initial_capital=10000.0,
        final_capital=10000.0,
        total_return_pct=0.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=0.0,
        num_trades=0,
        win_rate=0.0,
        profit_factor=0.0,
        equity_curve=[],
    )

    assert len(result.equity_curve) == 0

    # Should still serialize/deserialize
    json_str = result.to_json()
    restored = BacktestResult.from_json(json_str)
    assert len(restored.equity_curve) == 0


def test_equity_curve_large() -> None:
    """Test result with large equity curve."""
    # Simulate 1 year of minute bars
    equity_curve = [(i * 60_000_000_000, 10000.0 + i * 0.1) for i in range(365 * 24 * 60)]

    result = BacktestResult(
        strategy_id="large_curve_test",
        symbol="ATOM/USDT",
        start_ts=equity_curve[0][0],
        end_ts=equity_curve[-1][0],
        initial_capital=10000.0,
        final_capital=equity_curve[-1][1],
        total_return_pct=50.0,
        sharpe_ratio=2.0,
        max_drawdown_pct=10.0,
        num_trades=1000,
        win_rate=0.55,
        profit_factor=1.8,
        equity_curve=equity_curve,
    )

    # Should serialize (even if large)
    json_str = result.to_json()
    assert len(json_str) > 0

    # Should deserialize
    restored = BacktestResult.from_json(json_str)
    assert len(restored.equity_curve) == len(equity_curve)
