from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from core.contracts import OrderIntent


@dataclass(frozen=True)
class BrokerOrderReq:
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"]
    qty: float
    limit_price: float | None
    client_order_id: str


@dataclass(frozen=True)
class BrokerOrderAck:
    client_order_id: str
    exchange_order_id: str
    ts_ns: int


@dataclass(frozen=True)
class BrokerOrderUpdate:
    exchange_order_id: str
    status: Literal["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED"]
    filled_qty: float
    avg_price: float | None
    ts_ns: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BalanceSnapshot:
    asset: str
    free: float
    locked: float
    ts_ns: int


class IBroker(ABC):
    @abstractmethod
    def place(self, req: BrokerOrderReq) -> BrokerOrderAck:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, exchange_order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_orders(self, symbol: str | None = None) -> list[BrokerOrderUpdate]:
        raise NotImplementedError

    @abstractmethod
    def fetch_balances(self) -> list[BalanceSnapshot]:
        raise NotImplementedError


CLIENT_ID_PREFIX = "NJ-"


def map_intent_to_broker(intent: OrderIntent) -> BrokerOrderReq:
    client_order_id = f"{CLIENT_ID_PREFIX}{intent.id[:20]}"
    return BrokerOrderReq(
        symbol=intent.symbol,
        side=intent.side,
        type=intent.type,
        qty=float(intent.qty),
        limit_price=intent.limit_price,
        client_order_id=client_order_id,
    )
