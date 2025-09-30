from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class OrderIntent:
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
    tag: str = ""
