"""Backtest contracts and data structures."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for a backtest run."""

    symbol: str
    strategy_id: str
    start_ts: int  # epoch nanoseconds
    end_ts: int  # epoch nanoseconds
    initial_capital: float
    commission_rate: float  # e.g., 0.001 = 0.1%
    slippage_bps: float  # basis points (e.g., 5 = 0.05%)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.start_ts >= self.end_ts:
            raise ValueError("start_ts must be before end_ts")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.commission_rate < 0:
            raise ValueError("commission_rate cannot be negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps cannot be negative")


@dataclass(frozen=True)
class BacktestResult:
    """Results from a backtest run."""

    strategy_id: str
    symbol: str
    start_ts: int  # epoch nanoseconds
    end_ts: int  # epoch nanoseconds
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    num_trades: int
    win_rate: float  # 0.0 to 1.0
    profit_factor: float  # gross profit / gross loss
    equity_curve: list[tuple[int, float]]  # (ts_ns, capital)

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary with JSON-serializable equity curve."""
        result = asdict(self)
        # Equity curve is already JSON-serializable (list of tuples)
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BacktestResult:
        """Create from dictionary."""
        # Convert equity curve from list of lists to list of tuples
        if "equity_curve" in data:
            equity_curve = data["equity_curve"]
            # Handle both list of tuples and list of lists
            if (
                isinstance(equity_curve, list)
                and equity_curve
                and isinstance(equity_curve[0], list)
            ):
                data["equity_curve"] = [(int(ts), float(val)) for ts, val in equity_curve]

        return cls(**data)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, json_str: str) -> BacktestResult:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
