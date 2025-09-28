from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any

@dataclass(frozen=True)
class TradeEvent:
    ts_local_ns: int
    ts_exchange_ms: Optional[int]
    symbol: str
    side: str
    qty: float
    price: float
    agg_id: Optional[str] = None

@dataclass(frozen=True)
class BookEvent:
    ts_local_ns: int
    symbol: str
    bids: List[Tuple[float, float]]
    asks: List[Tuple[float, float]]
    checksum: Optional[int] = None

@dataclass(frozen=True)
class OrderIntent:
    ts_local_ns: int
    strategy_id: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    type: str  # "market" | "limit"
    limit_price: Optional[float] = None
    tif: str = "GTC"
    meta: Dict[str, Any] = None
