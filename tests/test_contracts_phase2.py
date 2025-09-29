from __future__ import annotations

from core.contracts import (
    Event2,
    FillEvent,
    OrderEvent,
    OrderIntent,
    PositionSnapshot,
    RiskDecision,
)


def test_order_intent_init() -> None:
    intent = OrderIntent(
        id="abc-123",
        ts_local_ns=1,
        strategy_id="strat-1",
        symbol="ATOM/USDT",
        side="buy",
        type="limit",
        qty=1.5,
        limit_price=12.34,
    )

    assert intent.id == "abc-123"
    assert intent.meta == {}


def test_risk_decision_init() -> None:
    decision = RiskDecision(intent_id="abc-123", allowed=True, reason=None)
    assert decision.intent_id == "abc-123"
    assert decision.allowed is True
    assert decision.caps == {}


def test_order_event_init() -> None:
    event = OrderEvent(
        intent_id="abc-123",
        venue="binanceus",
        symbol="ATOM/USDT",
        side="buy",
        type="limit",
        qty=1.5,
        limit_price=12.34,
        ts_accepted_ns=42,
    )
    assert event.intent_id == "abc-123"
    assert event.ts_accepted_ns == 42


def test_fill_event_init() -> None:
    fill = FillEvent(
        order_id="order-1",
        symbol="ATOM/USDT",
        side="buy",
        qty=1.5,
        price=12.5,
        ts_fill_ns=84,
    )
    assert fill.fee == 0.0
    assert fill.price == 12.5


def test_position_snapshot_init() -> None:
    snap = PositionSnapshot(
        symbol="ATOM/USDT",
        qty=3.0,
        avg_price=11.5,
        realized_pnl=2.0,
        ts_ns=168,
    )
    assert snap.symbol == "ATOM/USDT"
    assert snap.qty == 3.0


def test_event2_union_allows_all_models() -> None:
    events: list[Event2] = [
        OrderIntent(
            id="1",
            ts_local_ns=0,
            strategy_id="s",
            symbol="ATOM/USDT",
            side="buy",
            type="market",
            qty=1.0,
            limit_price=None,
        ),
        RiskDecision(intent_id="1", allowed=False, reason="cap exceeded"),
        OrderEvent(
            intent_id="1",
            venue="binanceus",
            symbol="ATOM/USDT",
            side="buy",
            type="market",
            qty=1.0,
            limit_price=None,
            ts_accepted_ns=1,
        ),
        FillEvent(
            order_id="o1",
            symbol="ATOM/USDT",
            side="buy",
            qty=1.0,
            price=12.0,
            ts_fill_ns=2,
        ),
        PositionSnapshot(
            symbol="ATOM/USDT",
            qty=1.0,
            avg_price=12.0,
            realized_pnl=0.0,
            ts_ns=3,
        ),
    ]

    assert len(events) == 5
