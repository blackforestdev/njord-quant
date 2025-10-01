"""Golden backtest tests - snapshot tests for deterministic results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backtest.contracts import BacktestConfig
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from strategies.base import StrategyBase


class GoldenStrategy(StrategyBase):
    """Strategy that follows a predefined trade schedule."""

    def __init__(self, strategy_id: str, trades: list[dict[str, Any]]) -> None:
        """Initialize golden strategy.

        Args:
            strategy_id: Strategy identifier
            trades: List of trade dicts with 'side' and 'bar_index'
        """
        self.strategy_id = strategy_id
        self.trades = trades
        self.bar_index = 0

    def on_event(self, event: Any) -> list[Any]:
        """Execute predefined trades at scheduled bars.

        Args:
            event: Bar event

        Returns:
            List of order intents
        """
        from core.contracts import OrderIntent

        intents = []

        # Check if we should trade at this bar
        for trade in self.trades:
            if trade["bar_index"] == self.bar_index:
                # Create order intent
                intent = OrderIntent(
                    id=f"{self.strategy_id}_{self.bar_index}",
                    ts_local_ns=0,
                    strategy_id=self.strategy_id,
                    symbol="ATOM/USDT",
                    side=trade["side"],
                    type="market",
                    qty=98.0,  # Fixed quantity (fits in $10k at ~$100/unit)
                    limit_price=None,
                )
                intents.append(intent)

        self.bar_index += 1
        return intents


def load_golden_test(test_name: str) -> dict[str, Any]:
    """Load golden test data from JSON file.

    Args:
        test_name: Test name (e.g., 'buy_hold')

    Returns:
        Golden test data
    """
    test_path = Path(__file__).parent / "golden" / f"backtest_{test_name}.json"
    with test_path.open() as f:
        data: dict[str, Any] = json.load(f)
        return data


def run_golden_backtest(golden_data: dict[str, Any]) -> dict[str, float]:
    """Run backtest from golden test data.

    Args:
        golden_data: Golden test configuration

    Returns:
        Computed metrics
    """
    config_data = golden_data["config"]
    bars_data = golden_data["bars"]
    trades_data = golden_data["trades"]

    # Create backtest config
    config = BacktestConfig(
        symbol=config_data["symbol"],
        strategy_id=config_data["strategy_id"],
        start_ts=bars_data[0]["ts_open"],
        end_ts=bars_data[-1]["ts_open"],
        initial_capital=config_data["initial_capital"],
        commission_rate=config_data["commission_rate"],
        slippage_bps=config_data["slippage_bps"],
    )

    # Create strategy
    strategy = GoldenStrategy(
        strategy_id=config_data["strategy_id"],
        trades=trades_data,
    )

    # Create temporary journal with test bars
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Write bars to journal
        symbol_clean = config.symbol.replace("/", "")
        journal_path = journal_dir / f"ohlcv.1m.{symbol_clean}.ndjson"

        with journal_path.open("w") as f:
            for bar in bars_data:
                bar_dict = {
                    "symbol": config.symbol,
                    "timeframe": "1m",
                    "ts_open": bar["ts_open"],
                    "ts_close": bar["ts_open"] + 60_000_000_000,  # +1 minute
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "volume": bar["volume"],
                }
                f.write(json.dumps(bar_dict) + "\n")

        # Run backtest
        engine = BacktestEngine(
            config=config,
            strategy=strategy,
            journal_dir=journal_dir,
        )

        result = engine.run()

        # Calculate metrics
        metrics = calculate_metrics(
            equity_curve=result.equity_curve,
            trades=engine.trades,
        )

        # Add num_trades
        metrics["num_trades"] = result.num_trades

        return metrics


def compare_metrics(
    computed: dict[str, float],
    expected: dict[str, float],
    tolerance: float = 0.0001,
) -> tuple[bool, str]:
    """Compare computed metrics with expected metrics.

    Args:
        computed: Computed metrics
        expected: Expected metrics
        tolerance: Tolerance for floating-point comparison (0.01% = 0.0001)

    Returns:
        Tuple of (passed, error_message)
    """
    for key, expected_value in expected.items():
        if key not in computed:
            return False, f"Missing metric: {key}"

        computed_value = computed[key]

        # Calculate relative difference
        if expected_value == 0.0:
            # For zero values, use absolute difference
            diff = abs(computed_value - expected_value)
            if diff > tolerance:
                return (
                    False,
                    f"{key}: expected {expected_value}, got {computed_value} (diff: {diff})",
                )
        else:
            # For non-zero values, use relative difference
            rel_diff = abs(computed_value - expected_value) / abs(expected_value)
            if rel_diff > tolerance:
                return (
                    False,
                    f"{key}: expected {expected_value}, got {computed_value} (rel_diff: {rel_diff * 100:.4f}%)",
                )

    return True, ""


# Golden tests


def test_golden_buy_hold() -> None:
    """Test buy and hold strategy."""
    golden_data = load_golden_test("buy_hold")
    metrics = run_golden_backtest(golden_data)
    expected = golden_data["expected_metrics"]

    passed, error = compare_metrics(metrics, expected)
    assert passed, error


def test_golden_volatile() -> None:
    """Test volatile strategy with multiple trades."""
    golden_data = load_golden_test("volatile")
    metrics = run_golden_backtest(golden_data)
    expected = golden_data["expected_metrics"]

    passed, error = compare_metrics(metrics, expected)
    assert passed, error


def test_golden_losing() -> None:
    """Test losing strategy with negative returns."""
    golden_data = load_golden_test("losing")
    metrics = run_golden_backtest(golden_data)
    expected = golden_data["expected_metrics"]

    passed, error = compare_metrics(metrics, expected)
    assert passed, error


def test_golden_determinism() -> None:
    """Test that backtests are deterministic across multiple runs."""
    golden_data = load_golden_test("buy_hold")

    # Run backtest twice
    metrics1 = run_golden_backtest(golden_data)
    metrics2 = run_golden_backtest(golden_data)

    # Compare results
    passed, error = compare_metrics(metrics1, metrics2, tolerance=0.0)
    assert passed, f"Backtest not deterministic: {error}"


def test_golden_tolerance() -> None:
    """Test that tolerance works correctly."""
    # Create slightly different metrics
    computed = {"total_return_pct": 20.0001, "sharpe_ratio": 1.5}
    expected = {"total_return_pct": 20.0, "sharpe_ratio": 1.5}

    # Should pass with 0.01% tolerance
    passed, _ = compare_metrics(computed, expected, tolerance=0.0001)
    assert passed

    # Should fail with tighter tolerance
    passed, _ = compare_metrics(computed, expected, tolerance=0.000001)
    assert not passed
