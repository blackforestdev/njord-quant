"""Fill simulator for realistic backtest order execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OHLCVBar:
    """OHLCV bar data for fill simulation."""

    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FillResult:
    """Result of fill simulation."""

    filled: bool
    fill_price: float
    qty: float
    commission: float


class FillSimulator:
    """Simulate order fills with realistic assumptions."""

    def __init__(self, commission_rate: float, slippage_bps: float) -> None:
        """Initialize fill simulator.

        Args:
            commission_rate: Commission rate (e.g., 0.001 = 0.1%)
            slippage_bps: Slippage in basis points (e.g., 5 = 0.05%)
        """
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps

    def simulate_market_order(self, side: str, qty: float, bar: OHLCVBar) -> FillResult:
        """Simulate market order fill.

        Args:
            side: "buy" or "sell"
            qty: Order quantity
            bar: Current OHLCV bar

        Returns:
            FillResult with fill details
        """
        # Market orders fill at bar close with slippage
        base_price = bar.close

        # Apply slippage asymmetrically
        # Buy: pay more (positive slippage)
        # Sell: receive less (negative slippage)
        slippage_factor = self.slippage_bps / 10000.0

        if side == "buy":
            fill_price = base_price * (1.0 + slippage_factor)
        else:  # sell
            fill_price = base_price * (1.0 - slippage_factor)

        # Calculate commission
        commission = qty * fill_price * self.commission_rate

        return FillResult(
            filled=True,
            fill_price=fill_price,
            qty=qty,
            commission=commission,
        )

    def simulate_limit_order(
        self, side: str, qty: float, limit_price: float, bar: OHLCVBar
    ) -> FillResult:
        """Simulate limit order fill.

        Args:
            side: "buy" or "sell"
            qty: Order quantity
            limit_price: Limit price
            bar: Current OHLCV bar

        Returns:
            FillResult with fill details (filled=False if no fill)
        """
        filled = False
        fill_price = 0.0

        if side == "buy":
            # Buy limit: fill if bar low <= limit price
            if bar.low <= limit_price:
                filled = True
                fill_price = limit_price  # Fill at limit
        else:  # sell
            # Sell limit: fill if bar high >= limit price
            if bar.high >= limit_price:
                filled = True
                fill_price = limit_price  # Fill at limit

        if not filled:
            return FillResult(
                filled=False,
                fill_price=0.0,
                qty=0.0,
                commission=0.0,
            )

        # Calculate commission
        commission = qty * fill_price * self.commission_rate

        return FillResult(
            filled=True,
            fill_price=fill_price,
            qty=qty,
            commission=commission,
        )
