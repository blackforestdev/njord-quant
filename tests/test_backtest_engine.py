from __future__ import annotations

import json
import tempfile
from pathlib import Path

from backtest.contracts import BacktestConfig
from backtest.engine import BacktestEngine, Position
from core.contracts import OHLCVBar, OrderIntent
from execution.simulator import ExecutionSimulator
from execution.slippage import LinearSlippageModel
from strategies.base import StrategyBase


class BuyHoldStrategy(StrategyBase):
    """Simple buy-and-hold strategy for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.bought = False

    def configure(self, config: dict[str, object]) -> None:
        """Configure strategy."""
        pass

    def on_event(self, event: object) -> list[OrderIntent]:
        """Buy on first bar, hold forever."""
        if not self.bought:
            self.bought = True
            return [
                OrderIntent(
                    id="test1",
                    ts_local_ns=0,
                    strategy_id="buy_hold",
                    symbol="ATOM/USDT",
                    side="buy",
                    type="market",
                    qty=10.0,
                    limit_price=None,
                )
            ]
        return []


class BuySellStrategy(StrategyBase):
    """Buy then sell strategy for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.bar_count = 0

    def configure(self, config: dict[str, object]) -> None:
        """Configure strategy."""
        pass

    def on_event(self, event: object) -> list[OrderIntent]:
        """Buy on bar 0, sell on bar 5."""
        self.bar_count += 1

        if self.bar_count == 1:
            return [
                OrderIntent(
                    id="buy1",
                    ts_local_ns=0,
                    strategy_id="buy_sell",
                    symbol="ATOM/USDT",
                    side="buy",
                    type="market",
                    qty=10.0,
                    limit_price=None,
                )
            ]
        elif self.bar_count == 6:
            return [
                OrderIntent(
                    id="sell1",
                    ts_local_ns=0,
                    strategy_id="buy_sell",
                    symbol="ATOM/USDT",
                    side="sell",
                    type="market",
                    qty=10.0,
                    limit_price=None,
                )
            ]

        return []


class AlgoStrategy(StrategyBase):
    """Strategy that routes through execution simulator."""

    def __init__(self) -> None:
        super().__init__()
        self.sent = False

    def configure(self, config: dict[str, object]) -> None:
        """No-op for tests."""

    def on_event(self, event: object) -> list[OrderIntent]:
        if self.sent:
            return []
        self.sent = True
        return [
            OrderIntent(
                id="algo_order",
                ts_local_ns=0,
                strategy_id="algo",
                symbol="ATOM/USDT",
                side="buy",
                type="market",
                qty=5.0,
                limit_price=None,
                meta={
                    "execution": {
                        "algo_type": "TWAP",
                        "total_quantity": 5.0,
                        "duration_seconds": 300,
                        "executor_params": {"slice_count": 5, "order_type": "market"},
                    }
                },
            )
        ]


def create_test_journal(tmpdir: Path, bars: list[OHLCVBar]) -> None:
    """Create test journal file."""
    journal_file = tmpdir / "ohlcv.1m.ATOMUSDT.ndjson"

    with open(journal_file, "w") as f:
        for bar in bars:
            f.write(json.dumps(bar.__dict__) + "\n")


def test_position_update_buy() -> None:
    """Test position update with buy."""
    pos = Position()

    pos.update(10.0, 100.0)

    assert pos.qty == 10.0
    assert pos.avg_price == 100.0


def test_position_update_multiple_buys() -> None:
    """Test averaging with multiple buys."""
    pos = Position()

    pos.update(10.0, 100.0)  # 10 @ 100
    pos.update(10.0, 110.0)  # 10 @ 110

    assert pos.qty == 20.0
    assert pos.avg_price == 105.0  # (1000 + 1100) / 20


def test_position_update_sell() -> None:
    """Test position update with sell."""
    pos = Position()

    pos.update(10.0, 100.0)
    pos.update(-5.0, 110.0)  # Sell half

    assert pos.qty == 5.0


def test_backtest_engine_creation() -> None:
    """Test creating backtest engine."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=0,
            end_ts=1000000000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=0.0,
        )

        strategy = BuyHoldStrategy()
        engine = BacktestEngine(config, strategy, Path(tmpdir))

        assert engine.cash == 10000.0
        assert engine.position.qty == 0.0


def test_backtest_engine_buy_hold() -> None:
    """Test buy-and-hold backtest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create test bars - price increasing
        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000.0,
            )
            for i in range(10)
        ]

        create_test_journal(journal_dir, bars)

        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="buy_hold",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.0,  # No commission for simplicity
            slippage_bps=0.0,
        )

        strategy = BuyHoldStrategy()
        engine = BacktestEngine(config, strategy, journal_dir)

        result = engine.run()

        # Should buy 10 shares at 100, hold as price goes to 109
        # Final: 10 * 109 = 1090 + remaining cash
        assert result.num_trades == 1
        assert result.final_capital > result.initial_capital


def test_backtest_engine_buy_sell() -> None:
    """Test buy then sell strategy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        # Create test bars
        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000.0,
            )
            for i in range(10)
        ]

        create_test_journal(journal_dir, bars)

        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="buy_sell",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.0,
            slippage_bps=0.0,
        )

        strategy = BuySellStrategy()
        engine = BacktestEngine(config, strategy, journal_dir)

        result = engine.run()

        # Should have buy and sell
        assert result.num_trades == 2
        # Buy at 100, sell at 105, profit = 50
        assert result.total_return_pct > 0


def test_backtest_engine_execution_simulator_integration() -> None:
    """Backtest engine integrates ExecutionSimulator for algorithmic intents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0 + i * 0.5,
                volume=5_000.0,
            )
            for i in range(12)
        ]

        create_test_journal(journal_dir, bars)

        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="algo",
            start_ts=0,
            end_ts=1_000_000_000_000,
            initial_capital=10_000.0,
            commission_rate=0.001,
            slippage_bps=5.0,
        )

        simulator = ExecutionSimulator(slippage_model=LinearSlippageModel(impact_coefficient=0.001))
        strategy = AlgoStrategy()
        engine = BacktestEngine(config, strategy, journal_dir, execution_simulator=simulator)

        result = engine.run()

        assert result.num_trades == 1
        assert engine.position.qty == 5.0
        assert engine.cash < config.initial_capital


def test_backtest_deterministic() -> None:
    """Test that backtest is deterministic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1000.0,
            )
            for i in range(10)
        ]

        create_test_journal(journal_dir, bars)

        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.001,
            slippage_bps=0.0,
        )

        # Run twice
        strategy1 = BuyHoldStrategy()
        engine1 = BacktestEngine(config, strategy1, journal_dir)
        result1 = engine1.run()

        strategy2 = BuyHoldStrategy()
        engine2 = BacktestEngine(config, strategy2, journal_dir)
        result2 = engine2.run()

        # Results should be identical
        assert result1.final_capital == result2.final_capital
        assert result1.num_trades == result2.num_trades
        assert result1.equity_curve == result2.equity_curve


def test_backtest_commission() -> None:
    """Test that commission is applied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1000.0,
            )
            for i in range(5)
        ]

        create_test_journal(journal_dir, bars)

        # Run with no commission
        config_no_comm = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.0,
            slippage_bps=0.0,
        )

        strategy1 = BuyHoldStrategy()
        engine1 = BacktestEngine(config_no_comm, strategy1, journal_dir)
        result1 = engine1.run()

        # Run with commission
        config_with_comm = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.01,  # 1% commission
            slippage_bps=0.0,
        )

        strategy2 = BuyHoldStrategy()
        engine2 = BacktestEngine(config_with_comm, strategy2, journal_dir)
        result2 = engine2.run()

        # With commission should have less capital
        assert result2.final_capital < result1.final_capital


def test_backtest_equity_curve() -> None:
    """Test that equity curve is tracked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1000.0,
            )
            for i in range(10)
        ]

        create_test_journal(journal_dir, bars)

        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.0,
            slippage_bps=0.0,
        )

        strategy = BuyHoldStrategy()
        engine = BacktestEngine(config, strategy, journal_dir)
        result = engine.run()

        # Should have equity point for each bar
        assert len(result.equity_curve) == 10

        # First point should be initial capital (or close to it)
        assert result.equity_curve[0][1] > 0


def test_backtest_position_tracking() -> None:
    """Test accurate position tracking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir)

        bars = [
            OHLCVBar(
                symbol="ATOM/USDT",
                timeframe="1m",
                ts_open=i * 60_000_000_000,
                ts_close=(i + 1) * 60_000_000_000,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1000.0,
            )
            for i in range(10)
        ]

        create_test_journal(journal_dir, bars)

        config = BacktestConfig(
            symbol="ATOM/USDT",
            strategy_id="test",
            start_ts=0,
            end_ts=1000_000_000_000,
            initial_capital=10000.0,
            commission_rate=0.0,
            slippage_bps=0.0,
        )

        strategy = BuyHoldStrategy()
        engine = BacktestEngine(config, strategy, journal_dir)
        engine.run()

        # After buy-hold, should have position
        assert engine.position.qty > 0
