"""Tests for parameter sweep harness."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any

from backtest.param_sweep import ParameterSweep
from strategies.base import StrategyBase


class DummyStrategy(StrategyBase):
    """Dummy strategy for testing parameter sweep."""

    def __init__(self, param_a: int = 10, param_b: float = 0.5) -> None:
        """Initialize with parameters.

        Args:
            param_a: Integer parameter
            param_b: Float parameter
        """
        self.strategy_id = f"dummy_a{param_a}_b{param_b}"
        self.param_a = param_a
        self.param_b = param_b
        self.bar_count = 0

    def on_event(self, event: Any) -> list[Any]:
        """Generate simple trades based on parameters.

        Args:
            event: Bar event

        Returns:
            List of order intents
        """
        from core.contracts import OrderIntent

        intents = []

        # Simple logic: trade every param_a bars
        if self.bar_count % self.param_a == 0 and self.bar_count < 3:
            side: Any = "buy" if self.bar_count == 0 else "sell"
            intent = OrderIntent(
                id=f"{self.strategy_id}_{self.bar_count}",
                ts_local_ns=0,
                strategy_id=self.strategy_id,
                symbol="ATOM/USDT",
                side=side,
                type="market",
                qty=50.0,
                limit_price=None,
            )
            intents.append(intent)

        self.bar_count += 1
        return intents


def create_test_journal(journal_dir: Path, num_bars: int = 5) -> None:
    """Create test OHLCV journal.

    Args:
        journal_dir: Directory for journals
        num_bars: Number of bars to create
    """
    journal_path = journal_dir / "ohlcv.1m.ATOMUSDT.ndjson"

    with journal_path.open("w") as f:
        for i in range(num_bars):
            bar = {
                "symbol": "ATOM/USDT",
                "timeframe": "1m",
                "ts_open": i * 86400_000_000_000,
                "ts_close": (i + 1) * 86400_000_000_000,
                "open": 100.0 + i,
                "high": 102.0 + i,
                "low": 98.0 + i,
                "close": 100.0 + i,
                "volume": 1000.0,
            }
            f.write(json.dumps(bar) + "\n")


def test_parameter_sweep_initialization() -> None:
    """Test ParameterSweep initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        assert sweep.strategy_class == DummyStrategy
        assert sweep.symbol == "ATOM/USDT"
        assert sweep.param_ranges == {}


def test_add_param_range() -> None:
    """Test adding parameter ranges."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        sweep.add_param_range("param_a", [10, 20, 30])
        sweep.add_param_range("param_b", [0.5, 1.0])

        assert sweep.param_ranges["param_a"] == [10, 20, 30]
        assert sweep.param_ranges["param_b"] == [0.5, 1.0]


def test_run_sweep_single_param() -> None:
    """Test running sweep with single parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        create_test_journal(journal_dir, num_bars=5)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        sweep.add_param_range("param_a", [1, 2, 3])

        results = sweep.run()

        # Should have 3 results (one for each param_a value)
        assert len(results) == 3

        # Check that param_a values are present
        param_a_values = [r["param_a"] for r in results]
        assert set(param_a_values) == {1, 2, 3}

        # Check that metrics are present
        for result in results:
            assert "total_return_pct" in result
            assert "sharpe_ratio" in result
            assert "max_drawdown_pct" in result
            assert "num_trades" in result


def test_run_sweep_multiple_params() -> None:
    """Test running sweep with multiple parameters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        create_test_journal(journal_dir, num_bars=5)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        sweep.add_param_range("param_a", [1, 2])
        sweep.add_param_range("param_b", [0.5, 1.0])

        results = sweep.run()

        # Should have 4 results (2 x 2 combinations)
        assert len(results) == 4

        # Check all combinations present
        combinations = [(r["param_a"], r["param_b"]) for r in results]
        expected_combinations = [(1, 0.5), (1, 1.0), (2, 0.5), (2, 1.0)]
        assert set(combinations) == set(expected_combinations)


def test_run_sweep_sorting() -> None:
    """Test that results are sorted by specified metric."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        create_test_journal(journal_dir, num_bars=5)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        sweep.add_param_range("param_a", [1, 2, 3])

        # Sort by Sharpe ratio (default)
        results = sweep.run(sort_by="sharpe_ratio")

        # Check that results are sorted in descending order
        sharpe_ratios = [r["sharpe_ratio"] for r in results]
        assert sharpe_ratios == sorted(sharpe_ratios, reverse=True)


def test_run_sweep_no_params_raises() -> None:
    """Test that running sweep with no parameters raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        create_test_journal(journal_dir, num_bars=5)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        # Don't add any param ranges
        try:
            sweep.run()
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "No parameter ranges defined" in str(e)


def test_save_results() -> None:
    """Test saving results to CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)
        create_test_journal(journal_dir, num_bars=5)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        sweep.add_param_range("param_a", [1, 2])
        results = sweep.run()

        # Save results
        output_path = Path(tmpdir) / "results" / "sweep.csv"
        sweep.save_results(results, output_path)

        # Verify file exists
        assert output_path.exists()

        # Verify CSV is parseable
        with output_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Should have 2 rows
        assert len(rows) == 2

        # Check that columns are present
        assert "param_a" in rows[0]
        assert "total_return_pct" in rows[0]
        assert "sharpe_ratio" in rows[0]


def test_save_results_empty() -> None:
    """Test saving empty results doesn't create file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        sweep = ParameterSweep(
            strategy_class=DummyStrategy,
            symbol="ATOM/USDT",
            start_ts=0,
            end_ts=432000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
            journal_dir=journal_dir,
        )

        output_path = Path(tmpdir) / "results" / "sweep.csv"
        sweep.save_results([], output_path)

        # File should not exist
        assert not output_path.exists()
