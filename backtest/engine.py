"""Backtest engine for deterministic strategy evaluation."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from backtest.contracts import BacktestConfig, BacktestResult
from core.journal_reader import JournalReader
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
        bars = reader.read_bars(
            symbol=self.config.symbol,
            timeframe="1m",  # TODO: Make configurable
            start=self.config.start_ts,
            end=self.config.end_ts,
        )

        # Replay bars
        for bar in bars:
            # Convert bar to event dict for strategy
            event = asdict(bar)

            # Inject bar into strategy
            intents = list(self.strategy.on_event(event))

            # Process intents
            for intent in intents:
                self._process_intent(intent, bar.close)

            # Update equity curve
            equity = self._calculate_equity(bar.close)
            self.equity_curve.append((bar.ts_open, equity))

        # Calculate final metrics
        return self._calculate_results()

    def _process_intent(self, intent: object, current_price: float) -> None:
        """Process order intent and generate fill.

        Args:
            intent: OrderIntent from strategy
            current_price: Current bar close price for fills
        """
        # Extract intent data (duck typing)
        if not hasattr(intent, "side") or not hasattr(intent, "qty"):
            return

        side = intent.side
        qty = intent.qty

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
            # Only sell if we have position
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
