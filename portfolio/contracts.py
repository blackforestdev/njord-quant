"""Portfolio allocation contracts and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyAllocation:
    """Strategy allocation configuration.

    Defines capital allocation for a single strategy within a portfolio.

    Attributes:
        strategy_id: Unique strategy identifier
        target_weight: Target weight (0.0 to 1.0)
        min_weight: Minimum allowed weight (default: 0.0)
        max_weight: Maximum allowed weight (default: 1.0)
        enabled: Whether strategy is active (default: True)
    """

    strategy_id: str
    target_weight: float
    min_weight: float = 0.0
    max_weight: float = 1.0
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate allocation parameters."""
        if not 0.0 <= self.target_weight <= 1.0:
            raise ValueError(f"target_weight must be in [0.0, 1.0], got {self.target_weight}")
        if not 0.0 <= self.min_weight <= 1.0:
            raise ValueError(f"min_weight must be in [0.0, 1.0], got {self.min_weight}")
        if not 0.0 <= self.max_weight <= 1.0:
            raise ValueError(f"max_weight must be in [0.0, 1.0], got {self.max_weight}")
        if self.min_weight > self.target_weight:
            raise ValueError(
                f"min_weight ({self.min_weight}) must be <= target_weight ({self.target_weight})"
            )
        if self.target_weight > self.max_weight:
            raise ValueError(
                f"target_weight ({self.target_weight}) must be <= max_weight ({self.max_weight})"
            )


@dataclass(frozen=True)
class PortfolioConfig:
    """Portfolio configuration.

    Defines portfolio-wide settings including strategy allocations and rebalancing rules.

    Attributes:
        portfolio_id: Unique portfolio identifier
        allocations: List of strategy allocations
        total_capital: Total portfolio capital
        rebalance_threshold_pct: Drift threshold triggering rebalance (default: 5.0%)
        min_rebalance_interval_sec: Minimum seconds between rebalances (default: 86400 = 1 day)
        allow_fractional: Allow fractional position sizes (default: False)
    """

    portfolio_id: str
    allocations: tuple[StrategyAllocation, ...]
    total_capital: float
    rebalance_threshold_pct: float = 5.0
    min_rebalance_interval_sec: int = 86400
    allow_fractional: bool = False

    def __post_init__(self) -> None:
        """Validate portfolio configuration."""
        if self.total_capital <= 0:
            raise ValueError(f"total_capital must be positive, got {self.total_capital}")
        if self.rebalance_threshold_pct < 0:
            raise ValueError(
                f"rebalance_threshold_pct must be non-negative, got {self.rebalance_threshold_pct}"
            )
        if self.min_rebalance_interval_sec < 0:
            raise ValueError(
                f"min_rebalance_interval_sec must be non-negative, got {self.min_rebalance_interval_sec}"
            )

        # Validate allocation weights sum to ~1.0
        total_target_weight = sum(
            alloc.target_weight for alloc in self.allocations if alloc.enabled
        )
        if abs(total_target_weight - 1.0) > 0.001:
            raise ValueError(
                f"Sum of enabled target_weights must be ~1.0, got {total_target_weight}"
            )

        # Check for duplicate strategy IDs
        strategy_ids = [alloc.strategy_id for alloc in self.allocations]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("Duplicate strategy_id found in allocations")

    def get_allocation(self, strategy_id: str) -> StrategyAllocation | None:
        """Get allocation for specific strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            StrategyAllocation if found, None otherwise
        """
        for alloc in self.allocations:
            if alloc.strategy_id == strategy_id:
                return alloc
        return None

    def enabled_allocations(self) -> list[StrategyAllocation]:
        """Get list of enabled allocations.

        Returns:
            List of enabled StrategyAllocation objects
        """
        return [alloc for alloc in self.allocations if alloc.enabled]


@dataclass
class StrategyPosition:
    """Current position state for a strategy.

    Attributes:
        strategy_id: Strategy identifier
        symbol: Trading symbol
        qty: Current quantity (positive for long, negative for short)
        avg_entry_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized P&L
        allocated_capital: Capital allocated to this strategy
    """

    strategy_id: str
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    allocated_capital: float

    @property
    def market_value(self) -> float:
        """Calculate current market value of position.

        Returns:
            Market value (qty * current_price)
        """
        return self.qty * self.current_price

    @property
    def weight(self) -> float:
        """Calculate position weight relative to allocated capital.

        Returns:
            Weight (market_value / allocated_capital)
        """
        if self.allocated_capital == 0:
            return 0.0
        return self.market_value / self.allocated_capital


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio state at a point in time.

    Attributes:
        ts_ns: Timestamp (epoch nanoseconds)
        portfolio_id: Portfolio identifier
        total_equity: Total portfolio equity (cash + positions)
        cash: Available cash
        positions: List of strategy positions
        last_rebalance_ts: Timestamp of last rebalance (epoch ns)
    """

    ts_ns: int
    portfolio_id: str
    total_equity: float
    cash: float
    positions: list[StrategyPosition] = field(default_factory=list)
    last_rebalance_ts: int = 0

    @property
    def total_position_value(self) -> float:
        """Calculate total value of all positions.

        Returns:
            Sum of market values
        """
        return sum(pos.market_value for pos in self.positions)

    @property
    def total_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L across all positions.

        Returns:
            Sum of unrealized P&L
        """
        return sum(pos.unrealized_pnl for pos in self.positions)

    def get_position(self, strategy_id: str, symbol: str) -> StrategyPosition | None:
        """Get position for specific strategy and symbol.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol

        Returns:
            StrategyPosition if found, None otherwise
        """
        for pos in self.positions:
            if pos.strategy_id == strategy_id and pos.symbol == symbol:
                return pos
        return None

    def get_strategy_positions(self, strategy_id: str) -> list[StrategyPosition]:
        """Get all positions for a specific strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of StrategyPosition objects for the strategy
        """
        return [pos for pos in self.positions if pos.strategy_id == strategy_id]
