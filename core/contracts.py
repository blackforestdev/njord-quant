from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TradeEvent:
    ts_local_ns: int
    ts_exchange_ms: int | None
    symbol: str
    side: str
    qty: float
    price: float
    agg_id: str | None = None


@dataclass(frozen=True)
class BookEvent:
    ts_local_ns: int
    symbol: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    checksum: int | None = None


@dataclass(frozen=True)
class OrderIntent:
    id: str
    ts_local_ns: int
    strategy_id: str
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"]
    qty: float
    limit_price: float | None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskDecision:
    intent_id: str
    allowed: bool
    reason: str | None
    caps: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderEvent:
    intent_id: str
    venue: str
    symbol: str
    side: str
    type: str
    qty: float
    limit_price: float | None
    ts_accepted_ns: int


@dataclass(frozen=True)
class FillEvent:
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    ts_fill_ns: int
    fee: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    qty: float
    avg_price: float
    realized_pnl: float
    ts_ns: int


Event2 = OrderIntent | RiskDecision | OrderEvent | FillEvent | PositionSnapshot
