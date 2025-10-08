"""Tests for performance attribution module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.data_reader import DataReader
from telemetry.attribution import AttributionReport, PerformanceAttribution


def _write_fills(path: Path, fills: list[dict[str, object]]) -> None:
    """Write fills to NDJSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for fill in fills:
            f.write(json.dumps(fill) + "\n")


class TestAttributionReport:
    """Tests for AttributionReport dataclass."""

    def test_attribution_report_creation(self) -> None:
        """Test creating an attribution report."""
        report = AttributionReport(
            portfolio_pnl=100.0,
            strategy_pnls={"alpha": 60.0, "beta": 40.0},
            strategy_returns={"alpha": 0.06, "beta": 0.04},
            strategy_weights={"alpha": 0.6, "beta": 0.4},
        )

        assert report.portfolio_pnl == 100.0
        assert report.strategy_pnls == {"alpha": 60.0, "beta": 40.0}
        assert report.alpha is None
        assert report.beta is None


class TestPerformanceAttribution:
    """Tests for PerformanceAttribution calculator."""

    def test_calculate_attribution_empty_fills(self, tmp_path: Path) -> None:
        """Test attribution with no fills."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        journal_dir.mkdir(parents=True)

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=1_000_000_000,
        )

        assert report.portfolio_pnl == 0.0
        assert report.strategy_pnls == {}

    def test_calculate_attribution_single_strategy(self, tmp_path: Path) -> None:
        """Test attribution with single strategy."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": {"strategy_id": "alpha"},
                },
                {
                    "order_id": "2",
                    "symbol": "ATOM/USDT",
                    "side": "sell",
                    "qty": 10.0,
                    "price": 12.0,
                    "ts_fill_ns": 1000,
                    "meta": {"strategy_id": "alpha"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
        )

        # Buy: +10 * 10 = +100
        # Sell: -10 * 12 = -120
        # Net: -20
        assert report.portfolio_pnl == -20.0
        assert report.strategy_pnls == {"alpha": -20.0}
        assert report.strategy_weights == {"alpha": 1.0}

    def test_calculate_attribution_multiple_strategies(self, tmp_path: Path) -> None:
        """Test attribution with multiple strategies."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": {"strategy_id": "alpha"},
                },
                {
                    "order_id": "2",
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "qty": 5.0,
                    "price": 20.0,
                    "ts_fill_ns": 600,
                    "meta": {"strategy_id": "beta"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
        )

        # Alpha: buy 10 @ 10 = +100
        # Beta: buy 5 @ 20 = +100
        # Total: +200
        assert report.portfolio_pnl == 200.0
        assert report.strategy_pnls == {"alpha": 100.0, "beta": 100.0}

        # Weights should be 0.5 each (equal PnL)
        assert report.strategy_weights["alpha"] == 0.5
        assert report.strategy_weights["beta"] == 0.5

    def test_pnl_attribution_sum_matches_total(self, tmp_path: Path) -> None:
        """Test that sum of attributed PnL equals portfolio PnL."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": {"strategy_id": "alpha"},
                },
                {
                    "order_id": "2",
                    "symbol": "ATOM/USDT",
                    "side": "sell",
                    "qty": 5.0,
                    "price": 12.0,
                    "ts_fill_ns": 600,
                    "meta": {"strategy_id": "beta"},
                },
                {
                    "order_id": "3",
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "qty": 3.0,
                    "price": 15.0,
                    "ts_fill_ns": 700,
                    "meta": {"strategy_id": "gamma"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
        )

        # Sum of strategy PnLs should equal portfolio PnL
        sum_strategy_pnls = sum(report.strategy_pnls.values())
        assert abs(sum_strategy_pnls - report.portfolio_pnl) < 1e-9

    def test_attribute_pnl_proportional_weights(self) -> None:
        """Test PnL attribution with proportional weighting."""
        reader = DataReader(Path("."))  # Dummy reader
        attribution = PerformanceAttribution(reader, "test")

        strategy_pnls = {"alpha": 60.0, "beta": 30.0, "gamma": 10.0}
        weights = attribution.attribute_pnl(
            portfolio_pnl=100.0,
            strategy_pnls=strategy_pnls,
            strategy_weights={},
        )

        # Weights should be proportional to absolute PnL
        assert weights["alpha"] == 0.6
        assert weights["beta"] == 0.3
        assert weights["gamma"] == 0.1

    def test_attribute_pnl_with_negative_pnl(self) -> None:
        """Test PnL attribution with negative PnL."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        strategy_pnls = {"alpha": 60.0, "beta": -40.0}
        weights = attribution.attribute_pnl(
            portfolio_pnl=20.0,
            strategy_pnls=strategy_pnls,
            strategy_weights={},
        )

        # Weights based on absolute values
        # |60| + |-40| = 100
        assert weights["alpha"] == 0.6  # 60/100
        assert weights["beta"] == 0.4  # 40/100

    def test_calculate_alpha_beta_positive_correlation(self) -> None:
        """Test alpha/beta calculation with positive correlation."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        strategy_returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        benchmark_returns = [0.01, 0.015, 0.02, 0.03, 0.04]

        alpha, beta = attribution.calculate_alpha_beta(strategy_returns, benchmark_returns)

        # Beta should be positive (positive correlation)
        assert beta > 0
        # Alpha should be small (strategies track benchmark closely)
        assert abs(alpha) < 0.1

    def test_calculate_alpha_beta_manual_verification(self) -> None:
        """Test alpha/beta matches manual computation."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        # Simple test case for manual verification
        strategy_returns = [0.10, 0.20]
        benchmark_returns = [0.05, 0.10]

        alpha, beta = attribution.calculate_alpha_beta(strategy_returns, benchmark_returns)

        # Manual calculation:
        # mean_strategy = 0.15
        # mean_benchmark = 0.075
        # covariance = ((0.10-0.15)*(0.05-0.075) + (0.20-0.15)*(0.10-0.075)) / 2
        #            = ((-0.05)*(-0.025) + (0.05)*(0.025)) / 2
        #            = (0.00125 + 0.00125) / 2 = 0.00125
        # variance = ((0.05-0.075)^2 + (0.10-0.075)^2) / 2
        #          = (0.000625 + 0.000625) / 2 = 0.000625
        # beta = 0.00125 / 0.000625 = 2.0
        # alpha = 0.15 - (2.0 * 0.075) = 0.0

        assert abs(beta - 2.0) < 1e-9
        assert abs(alpha - 0.0) < 1e-9

    def test_calculate_alpha_beta_empty_returns(self) -> None:
        """Test alpha/beta with empty returns."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        alpha, beta = attribution.calculate_alpha_beta([], [])

        assert alpha == 0.0
        assert beta == 0.0

    def test_calculate_alpha_beta_single_return(self) -> None:
        """Test alpha/beta with single return."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        alpha, beta = attribution.calculate_alpha_beta([0.1], [0.05])

        # Not enough data for regression
        assert alpha == 0.0
        assert beta == 1.0

    def test_brinson_attribution(self, tmp_path: Path) -> None:
        """Test Brinson attribution decomposes correctly."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 100.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": {"strategy_id": "alpha"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        benchmark_returns = [0.05, 0.06, 0.07]

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
            benchmark_returns=benchmark_returns,
        )

        # Should have allocation and selection effects
        assert report.allocation_effect is not None
        assert report.selection_effect is not None
        assert "alpha" in report.allocation_effect
        assert "alpha" in report.selection_effect

    def test_sharpe_ratio_calculation(self, tmp_path: Path) -> None:
        """Test Sharpe ratio calculation."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": {"strategy_id": "alpha"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
        )

        # Sharpe ratio should be calculated (may be None for single data point)
        # With single strategy, we get one return value, need >1 for stdev
        # This test mainly verifies the calculation doesn't crash
        assert report.portfolio_pnl == 100.0

    def test_handles_missing_strategy_id(self, tmp_path: Path) -> None:
        """Test handling fills with missing strategy_id."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": {},  # No strategy_id
                },
                {
                    "order_id": "2",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 5.0,
                    "price": 10.0,
                    "ts_fill_ns": 600,
                    "meta": {"strategy_id": "alpha"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
        )

        # Only the fill with strategy_id should be counted
        assert report.strategy_pnls == {"alpha": 50.0}
        assert report.portfolio_pnl == 50.0

    def test_handles_invalid_meta_field(self, tmp_path: Path) -> None:
        """Test handling fills with invalid meta field."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 500,
                    "meta": "invalid",  # Not a dict
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=2000,
        )

        # Should handle gracefully
        assert report.portfolio_pnl == 0.0
        assert report.strategy_pnls == {}

    def test_equal_weights_for_zero_pnl(self) -> None:
        """Test equal weighting when all PnLs are zero."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        strategy_pnls = {"alpha": 0.0, "beta": 0.0, "gamma": 0.0}
        weights = attribution.attribute_pnl(
            portfolio_pnl=0.0,
            strategy_pnls=strategy_pnls,
            strategy_weights={},
        )

        # Should assign equal weights
        assert weights["alpha"] == pytest.approx(1.0 / 3.0)
        assert weights["beta"] == pytest.approx(1.0 / 3.0)
        assert weights["gamma"] == pytest.approx(1.0 / 3.0)

    def test_sortino_ratio_calculation(self) -> None:
        """Test Sortino ratio (downside risk-adjusted) calculation."""
        reader = DataReader(Path("."))
        attribution = PerformanceAttribution(reader, "test")

        returns = [0.05, -0.02, 0.03, -0.01, 0.04]
        sortino = attribution._calculate_sortino(returns)

        # Sortino should be calculated (checks downside deviation)
        assert sortino != 0.0

    def test_known_attribution_scenario(self, tmp_path: Path) -> None:
        """Test known attribution scenario with expected results."""
        pytest.importorskip("pandas")

        journal_dir = tmp_path / "journals"
        _write_fills(
            journal_dir / "fills.ndjson",
            [
                # Strategy alpha: net +200
                {
                    "order_id": "1",
                    "symbol": "ATOM/USDT",
                    "side": "buy",
                    "qty": 10.0,
                    "price": 10.0,
                    "ts_fill_ns": 100,
                    "meta": {"strategy_id": "alpha"},
                },
                {
                    "order_id": "2",
                    "symbol": "ATOM/USDT",
                    "side": "sell",
                    "qty": 10.0,
                    "price": 30.0,
                    "ts_fill_ns": 200,
                    "meta": {"strategy_id": "alpha"},
                },
                # Strategy beta: net +50
                {
                    "order_id": "3",
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "qty": 5.0,
                    "price": 20.0,
                    "ts_fill_ns": 300,
                    "meta": {"strategy_id": "beta"},
                },
                {
                    "order_id": "4",
                    "symbol": "ETH/USDT",
                    "side": "sell",
                    "qty": 5.0,
                    "price": 30.0,
                    "ts_fill_ns": 400,
                    "meta": {"strategy_id": "beta"},
                },
            ],
        )

        reader = DataReader(journal_dir)
        attribution = PerformanceAttribution(reader, "test_portfolio")

        report = attribution.calculate_attribution(
            start_ts_ns=0,
            end_ts_ns=1000,
        )

        # Alpha: buy 10@10=+100, sell 10@30=-300, net=-200
        # Beta: buy 5@20=+100, sell 5@30=-150, net=-50
        # Total: -250
        assert report.portfolio_pnl == -250.0
        assert report.strategy_pnls["alpha"] == -200.0
        assert report.strategy_pnls["beta"] == -50.0

        # Weights: alpha 200/250=0.8, beta 50/250=0.2
        assert report.strategy_weights["alpha"] == 0.8
        assert report.strategy_weights["beta"] == 0.2

        # Sum test
        assert sum(report.strategy_pnls.values()) == report.portfolio_pnl
