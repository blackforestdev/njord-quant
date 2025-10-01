"""Equity curve tracking for backtest portfolio valuation."""

from __future__ import annotations


class EquityTracker:
    """Track portfolio equity over time during backtest."""

    def __init__(self, initial_capital: float) -> None:
        """Initialize equity tracker.

        Args:
            initial_capital: Starting capital
        """
        self.initial_capital = initial_capital
        self.equity_curve: list[tuple[int, float]] = []

    def record(self, ts_ns: int, cash: float, positions: dict[str, tuple[float, float]]) -> None:
        """Record equity snapshot at a point in time.

        Args:
            ts_ns: Timestamp in epoch nanoseconds
            cash: Available cash
            positions: Dict mapping symbol to (qty, current_price)
        """
        # Calculate total position value
        position_value = 0.0
        for qty, price in positions.values():
            position_value += qty * price

        # Total equity = cash + position value
        equity = cash + position_value

        # Store snapshot
        self.equity_curve.append((ts_ns, equity))

    def get_equity_curve(self) -> list[tuple[int, float]]:
        """Get the complete equity curve.

        Returns:
            List of (timestamp_ns, equity) tuples
        """
        return self.equity_curve.copy()

    def get_final_equity(self) -> float:
        """Get the final equity value.

        Returns:
            Final equity, or initial capital if no records
        """
        if not self.equity_curve:
            return self.initial_capital
        return self.equity_curve[-1][1]

    def get_peak_equity(self) -> float:
        """Get the peak equity value.

        Returns:
            Maximum equity reached, or initial capital if no records
        """
        if not self.equity_curve:
            return self.initial_capital
        return max(equity for _ts, equity in self.equity_curve)

    def get_current_drawdown(self) -> float:
        """Get the current drawdown from peak.

        Returns:
            Current drawdown as positive percentage
        """
        if not self.equity_curve:
            return 0.0

        peak = self.initial_capital
        current = self.equity_curve[-1][1]

        for _ts, equity in self.equity_curve:
            if equity > peak:
                peak = equity

        if peak == 0:
            return 0.0

        drawdown = ((peak - current) / peak) * 100.0
        return max(0.0, drawdown)
