"""Slippage models for realistic execution simulation.

This module implements slippage models to simulate market impact
and execution costs in backtesting. Models account for:
- Order size relative to market volume (price impact)
- Bid-ask spread crossing costs
- Temporary vs permanent impact

All slippage is calculated in price units (e.g., dollars per unit).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


class SlippageModel(ABC):
    """Abstract base class for slippage models.

    Slippage models estimate the price impact of executing an order
    based on order size, market conditions, and liquidity.

    All implementations must return slippage in PRICE UNITS (not basis points).
    """

    @abstractmethod
    def calculate_slippage(
        self,
        order_size: float,
        market_volume: float,
        bid_ask_spread: float,
        reference_price: float,
    ) -> float:
        """Calculate expected slippage in price units.

        Args:
            order_size: Order quantity (absolute value, not signed)
            market_volume: Average market volume over measurement period
            bid_ask_spread: Current bid-ask spread in price units
            reference_price: Reference price for impact calculation (e.g., mid price)

        Returns:
            Slippage in price units (always positive)

        Note:
            Slippage includes both:
            - Price impact: f(order_size / market_volume) * reference_price
            - Spread crossing: bid_ask_spread / 2 (assuming mid-price reference)

        Raises:
            ValueError: If market_volume <= 0 or reference_price <= 0
        """
        ...


class LinearSlippageModel(SlippageModel):
    """Linear slippage model: impact proportional to order size.

    Formula:
        impact = impact_coefficient * (order_size / market_volume) * reference_price
        total_slippage = impact + (bid_ask_spread / 2)

    This model assumes price impact grows linearly with order size
    relative to market volume. Suitable for small to medium orders
    in liquid markets.

    Attributes:
        impact_coefficient: Linear impact factor (default 0.001 = 0.1% impact at 100% volume)
    """

    def __init__(self, impact_coefficient: float = 0.001) -> None:
        """Initialize linear slippage model.

        Args:
            impact_coefficient: Linear impact factor (must be >= 0)

        Raises:
            ValueError: If impact_coefficient < 0
        """
        if impact_coefficient < 0:
            raise ValueError(f"impact_coefficient must be >= 0, got {impact_coefficient}")
        self.impact_coefficient = impact_coefficient

    def calculate_slippage(
        self,
        order_size: float,
        market_volume: float,
        bid_ask_spread: float,
        reference_price: float,
    ) -> float:
        """Calculate linear slippage.

        Args:
            order_size: Order quantity (absolute value)
            market_volume: Average market volume
            bid_ask_spread: Bid-ask spread in price units
            reference_price: Reference price for impact calculation

        Returns:
            Total slippage = price impact + spread cost

        Raises:
            ValueError: If order_size < 0, market_volume <= 0, bid_ask_spread < 0,
                or reference_price <= 0
        """
        if order_size < 0:
            raise ValueError(f"order_size must be >= 0, got {order_size}")
        if market_volume <= 0:
            raise ValueError(f"market_volume must be > 0, got {market_volume}")
        if bid_ask_spread < 0:
            raise ValueError(f"bid_ask_spread must be >= 0, got {bid_ask_spread}")
        if reference_price <= 0:
            raise ValueError(f"reference_price must be > 0, got {reference_price}")

        # Price impact: linear with order size ratio
        participation_rate = order_size / market_volume
        price_impact = self.impact_coefficient * participation_rate * reference_price

        # Spread crossing cost (half spread for aggressive order)
        spread_cost = bid_ask_spread / 2.0

        return price_impact + spread_cost


class SquareRootSlippageModel(SlippageModel):
    """Square-root slippage model: impact proportional to sqrt(order size).

    Formula:
        impact = impact_coefficient * sqrt(order_size / market_volume) * reference_price
        total_slippage = impact + (bid_ask_spread / 2)

    This model reflects empirical market microstructure research showing
    price impact grows with the square root of order size. More realistic
    for large orders and institutional execution.

    Based on Kyle (1985) and empirical studies of market impact.

    Attributes:
        impact_coefficient: Square-root impact factor (default 0.5)
    """

    def __init__(self, impact_coefficient: float = 0.5) -> None:
        """Initialize square-root slippage model.

        Args:
            impact_coefficient: Square-root impact factor (must be >= 0)

        Raises:
            ValueError: If impact_coefficient < 0
        """
        if impact_coefficient < 0:
            raise ValueError(f"impact_coefficient must be >= 0, got {impact_coefficient}")
        self.impact_coefficient = impact_coefficient

    def calculate_slippage(
        self,
        order_size: float,
        market_volume: float,
        bid_ask_spread: float,
        reference_price: float,
    ) -> float:
        """Calculate square-root slippage.

        Args:
            order_size: Order quantity (absolute value)
            market_volume: Average market volume
            bid_ask_spread: Bid-ask spread in price units
            reference_price: Reference price for impact calculation

        Returns:
            Total slippage = price impact + spread cost

        Raises:
            ValueError: If order_size < 0, market_volume <= 0, bid_ask_spread < 0,
                or reference_price <= 0
        """
        if order_size < 0:
            raise ValueError(f"order_size must be >= 0, got {order_size}")
        if market_volume <= 0:
            raise ValueError(f"market_volume must be > 0, got {market_volume}")
        if bid_ask_spread < 0:
            raise ValueError(f"bid_ask_spread must be >= 0, got {bid_ask_spread}")
        if reference_price <= 0:
            raise ValueError(f"reference_price must be > 0, got {reference_price}")

        # Price impact: square root of order size ratio
        participation_rate = order_size / market_volume
        price_impact = self.impact_coefficient * math.sqrt(participation_rate) * reference_price

        # Spread crossing cost (half spread for aggressive order)
        spread_cost = bid_ask_spread / 2.0

        return price_impact + spread_cost
