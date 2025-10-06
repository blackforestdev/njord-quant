"""Backtest engine for deterministic strategy evaluation."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from backtest.contracts import BacktestConfig, BacktestResult
from core.contracts import OrderIntent
from core.journal_reader import JournalReader
from execution.base import BaseExecutor
from execution.contracts import ExecutionAlgorithm, ExecutionReport
from execution.iceberg import IcebergExecutor
from execution.pov import POVExecutor
from execution.simulator import ExecutionSimulator
from execution.slippage import LinearSlippageModel
from execution.twap import TWAPExecutor
from execution.vwap import VWAPExecutor
from strategies.base import StrategyBase


class Position:
    """Track position state during backtest."""

    def __init__(self) -> None:
        self.qty: float = 0.0
        self.avg_price: float = 0.0

    def update(self, qty_delta: float, price: float) -> None:
        """Update position with new fill.

        Args:
            qty_delta: Change in quantity (positive for buy, negative for sell)
            price: Fill price
        """
        if qty_delta > 0:
            # Buying
            total_cost = (self.qty * self.avg_price) + (qty_delta * price)
            self.qty += qty_delta
            self.avg_price = total_cost / self.qty if self.qty > 0 else 0.0
        else:
            # Selling
            self.qty += qty_delta  # qty_delta is negative


class BacktestEngine:
    """Deterministic backtest engine."""

    def __init__(
        self,
        config: BacktestConfig,
        strategy: StrategyBase,
        journal_dir: Path,
        execution_simulator: ExecutionSimulator | None = None,
    ) -> None:
        """Initialize backtest engine.

        Args:
            config: Backtest configuration
            strategy: Strategy instance to test
            journal_dir: Directory containing OHLCV journals
        """
        self.config = config
        self.strategy = strategy
        self.journal_dir = journal_dir

        impact_coefficient = config.slippage_bps / 10_000 if config.slippage_bps > 0 else 0.0
        self.execution_simulator = execution_simulator or ExecutionSimulator(
            slippage_model=LinearSlippageModel(impact_coefficient=impact_coefficient)
        )

        # State
        self.cash = config.initial_capital
        self.position = Position()
        self.equity_curve: list[tuple[int, float]] = []
        self.trades: list[dict[str, object]] = []

    def run(self) -> BacktestResult:
        """Run backtest and return results.

        Returns:
            BacktestResult with performance metrics
        """
        # Load bars from journals
        reader = JournalReader(self.journal_dir)
        bars_iter = list(
            reader.read_bars(
                symbol=self.config.symbol,
                timeframe="1m",  # TODO: Make configurable
                start=self.config.start_ts,
                end=self.config.end_ts,
            )
        )

        if not bars_iter:
            return self._calculate_results()

        market_records = [asdict(bar) for bar in bars_iter]
        market_df = pd.DataFrame(market_records)

        # Replay bars
        for idx, bar in enumerate(bars_iter):
            event = market_records[idx]
            market_slice = market_df.iloc[idx:].reset_index(drop=True)

            # Inject bar into strategy
            intents = list(self.strategy.on_event(event))

            # Process intents
            for intent in intents:
                self._process_intent(intent, bar.close, market_slice)

            # Update equity curve
            equity = self._calculate_equity(bar.close)
            self.equity_curve.append((bar.ts_open, equity))

        # Calculate final metrics
        return self._calculate_results()

    def _process_intent(
        self,
        intent: object,
        current_price: float,
        market_slice: pd.DataFrame,
    ) -> None:
        """Process order intent and generate fill.

        Args:
            intent: OrderIntent from strategy
            current_price: Current bar close price for fills
        """
        # Extract intent data (duck typing)
        if not hasattr(intent, "side") or not hasattr(intent, "qty"):
            return

        order_intent = cast(OrderIntent, intent)
        side = order_intent.side
        qty = order_intent.qty

        execution_meta = order_intent.meta.get("execution")
        if (
            self.execution_simulator is not None
            and isinstance(execution_meta, dict)
            and execution_meta.get("algo_type")
        ):
            algo = self._build_execution_algorithm(order_intent, execution_meta)
            if algo.side == "buy" and self.cash <= 0:
                return
            if algo.side == "sell" and self.position.qty < algo.total_quantity:
                return

            executor = self._create_executor(order_intent.strategy_id, algo, execution_meta)
            report = self.execution_simulator.simulate_execution(executor, algo, market_slice)
            self._apply_execution_report(report, algo.side)
            return

        # Simple fill simulation (market order at close price)
        if side == "buy":
            cost = qty * current_price
            commission = cost * self.config.commission_rate

            if self.cash >= cost + commission:
                self.cash -= cost + commission
                self.position.update(qty, current_price)

                self.trades.append(
                    {
                        "side": "buy",
                        "qty": qty,
                        "price": current_price,
                        "commission": commission,
                    }
                )
        elif side == "sell":
            if self.position.qty >= qty:
                proceeds = qty * current_price
                commission = proceeds * self.config.commission_rate

                self.cash += proceeds - commission
                self.position.update(-qty, current_price)

                self.trades.append(
                    {
                        "side": "sell",
                        "qty": qty,
                        "price": current_price,
                        "commission": commission,
                    }
                )

    def _build_execution_algorithm(
        self,
        intent: OrderIntent,
        execution_meta: dict[str, object],
    ) -> ExecutionAlgorithm:
        order_intent = intent

        algo_value = execution_meta.get("algo_type", "TWAP")
        if algo_value not in {"TWAP", "VWAP", "Iceberg", "POV"}:
            raise ValueError(f"Unsupported execution algorithm: {algo_value}")
        algo_type = cast(Literal["TWAP", "VWAP", "Iceberg", "POV"], algo_value)

        qty_value = execution_meta.get("total_quantity", order_intent.qty)
        total_quantity = float(cast(float, qty_value))

        duration_value = execution_meta.get("duration_seconds", 1)
        duration_seconds = int(cast(int, duration_value))

        params = cast(dict[str, Any], execution_meta.get("params", {}))

        return ExecutionAlgorithm(
            algo_type=algo_type,
            symbol=order_intent.symbol,
            side=order_intent.side,
            total_quantity=total_quantity,
            duration_seconds=max(duration_seconds, 1),
            params=params,
        )

    def _create_executor(
        self,
        strategy_id: str,
        algo: ExecutionAlgorithm,
        execution_meta: dict[str, object],
    ) -> BaseExecutor:
        executor_params = cast(dict[str, Any], execution_meta.get("executor_params", {}))

        if algo.algo_type == "TWAP":
            slice_count = int(executor_params.get("slice_count", 1))
            order_value = executor_params.get("order_type", "market")
            order_type = cast(Literal["limit", "market"], order_value)
            return TWAPExecutor(
                strategy_id=strategy_id, slice_count=slice_count, order_type=order_type
            )

        if algo.algo_type == "VWAP":
            if self.execution_simulator.data_reader is None:
                raise ValueError("VWAP execution requires data_reader")
            slice_count = int(executor_params.get("slice_count", 1))
            order_value = executor_params.get("order_type", "market")
            order_type = cast(Literal["limit", "market"], order_value)
            return VWAPExecutor(
                strategy_id=strategy_id,
                data_reader=self.execution_simulator.data_reader,
                slice_count=slice_count,
                order_type=order_type,
            )

        if algo.algo_type == "Iceberg":
            visible_ratio = float(executor_params.get("visible_ratio", 0.1))
            replenish_threshold = float(executor_params.get("replenish_threshold", 0.5))
            return IcebergExecutor(
                strategy_id=strategy_id,
                visible_ratio=visible_ratio,
                replenish_threshold=replenish_threshold,
            )

        if algo.algo_type == "POV":
            if self.execution_simulator.data_reader is None:
                raise ValueError("POV execution requires data_reader")
            target_pov = float(executor_params.get("target_pov", 0.1))
            min_volume_threshold = float(executor_params.get("min_volume_threshold", 1000.0))
            return POVExecutor(
                strategy_id=strategy_id,
                data_reader=self.execution_simulator.data_reader,
                target_pov=target_pov,
                min_volume_threshold=min_volume_threshold,
            )

        raise ValueError(f"Unsupported execution algorithm: {algo.algo_type}")

    def _apply_execution_report(
        self,
        report: ExecutionReport,
        side: Literal["buy", "sell"],
    ) -> None:
        if report.filled_quantity <= 0:
            return

        notional = report.filled_quantity * report.avg_fill_price
        fees = report.total_fees

        if side == "buy":
            total_cost = notional + fees
            if self.cash < total_cost:
                return
            self.cash -= total_cost
            self.position.update(report.filled_quantity, report.avg_fill_price)
        else:
            if self.position.qty < report.filled_quantity:
                return
            self.cash += notional - fees
            self.position.update(-report.filled_quantity, report.avg_fill_price)

        self.trades.append(
            {
                "side": side,
                "qty": report.filled_quantity,
                "price": report.avg_fill_price,
                "commission": fees,
                "execution_id": report.execution_id,
            }
        )

    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current equity (cash + position value).

        Args:
            current_price: Current market price

        Returns:
            Total equity
        """
        position_value = self.position.qty * current_price
        return self.cash + position_value

    def _calculate_results(self) -> BacktestResult:
        """Calculate backtest results and metrics.

        Returns:
            BacktestResult with all metrics
        """
        final_capital = (
            self.equity_curve[-1][1] if self.equity_curve else self.config.initial_capital
        )

        # Calculate total return
        total_return_pct = (
            (final_capital - self.config.initial_capital) / self.config.initial_capital
        ) * 100.0

        # Calculate Sharpe ratio (simplified)
        sharpe_ratio = self._calculate_sharpe_ratio()

        # Calculate max drawdown
        max_drawdown_pct = self._calculate_max_drawdown()

        # Calculate trade statistics
        num_trades = len(self.trades)
        win_rate = self._calculate_win_rate()
        profit_factor = self._calculate_profit_factor()

        return BacktestResult(
            strategy_id=self.config.strategy_id,
            symbol=self.config.symbol,
            start_ts=self.config.start_ts,
            end_ts=self.config.end_ts,
            initial_capital=self.config.initial_capital,
            final_capital=final_capital,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_pct=max_drawdown_pct,
            num_trades=num_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            equity_curve=self.equity_curve,
        )

    def _calculate_sharpe_ratio(self) -> float:
        """Calculate annualized Sharpe ratio.

        Returns:
            Sharpe ratio (0.0 if insufficient data)
        """
        if len(self.equity_curve) < 2:
            return 0.0

        # Calculate returns
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i - 1][1]
            curr_equity = self.equity_curve[i][1]
            ret = (curr_equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
            returns.append(ret)

        if not returns:
            return 0.0

        # Calculate mean and std
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_return = variance**0.5

        if std_return == 0:
            return 0.0

        # Annualize (assuming daily returns)
        sharpe = (mean_return / std_return) * (365**0.5)
        return float(sharpe)

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown percentage.

        Returns:
            Max drawdown as positive percentage
        """
        if len(self.equity_curve) < 2:
            return 0.0

        max_drawdown = 0.0
        peak = self.equity_curve[0][1]

        for _ts, equity in self.equity_curve:
            if equity > peak:
                peak = equity

            drawdown = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def _calculate_win_rate(self) -> float:
        """Calculate win rate (fraction of profitable trades).

        Returns:
            Win rate between 0.0 and 1.0
        """
        if len(self.trades) < 2:
            return 0.0

        # Need to pair buy/sell trades
        wins = 0
        total_pairs = 0

        # Simple pairing: each sell after a buy
        buy_price = None
        for trade in self.trades:
            if trade["side"] == "buy":
                buy_price = trade["price"]
            elif trade["side"] == "sell" and buy_price is not None:
                sell_price = trade["price"]
                if sell_price > buy_price:  # type: ignore[operator]
                    wins += 1
                total_pairs += 1
                buy_price = None

        return wins / total_pairs if total_pairs > 0 else 0.0

    def _calculate_profit_factor(self) -> float:
        """Calculate profit factor (gross profit / gross loss).

        Returns:
            Profit factor (0.0 if no losing trades)
        """
        if len(self.trades) < 2:
            return 0.0

        gross_profit = 0.0
        gross_loss = 0.0

        # Pair buy/sell trades
        buy_price = None
        buy_qty = 0.0

        for trade in self.trades:
            if trade["side"] == "buy":
                buy_price = float(trade["price"])  # type: ignore[arg-type]
                buy_qty = float(trade["qty"])  # type: ignore[arg-type]
            elif trade["side"] == "sell" and buy_price is not None:
                sell_price = float(trade["price"])  # type: ignore[arg-type]
                sell_qty = float(trade["qty"])  # type: ignore[arg-type]

                pnl = (sell_price - buy_price) * min(buy_qty, sell_qty)

                if pnl > 0:
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)

                buy_price = None

        return gross_profit / gross_loss if gross_loss > 0 else 0.0
