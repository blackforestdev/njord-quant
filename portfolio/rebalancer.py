"""Portfolio rebalancing utilities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from core.contracts import OrderIntent
from portfolio.allocation import AllocationCalculator
from portfolio.contracts import PortfolioConfig, PortfolioSnapshot, StrategyPosition
from portfolio.position_sizer import PositionSizer


@dataclass(frozen=True)
class RebalancePlan:
    """Plan describing the trades needed to rebalance a portfolio."""

    portfolio_id: str
    timestamp_ns: int
    trades: list[OrderIntent]
    expected_drift_reduction: dict[str, float]
    estimated_costs: float


class Rebalancer:
    """Generate rebalancing `OrderIntent`s from portfolio drift."""

    def __init__(
        self,
        allocator: AllocationCalculator,
        sizer: PositionSizer,
        *,
        min_trade_value: float = 10.0,
        commission_rate: float = 0.0005,
        slippage_rate: float = 0.0005,
    ) -> None:
        self.allocator = allocator
        self.sizer = sizer
        self.min_trade_value = max(min_trade_value, 0.0)
        self.commission_rate = max(commission_rate, 0.0)
        self.slippage_rate = max(slippage_rate, 0.0)
        self.config: PortfolioConfig = allocator.config

    def create_rebalance_plan(
        self,
        snapshot: PortfolioSnapshot,
        current_prices: dict[str, float],
    ) -> RebalancePlan:
        """Generate a rebalancing plan for the provided snapshot."""

        allocations = self._compute_current_allocations(snapshot.positions, current_prices)
        targets = self.allocator.calculate_targets(current_allocations=allocations)
        drift = self.allocator.calculate_drift(allocations, targets)
        deltas = self.allocator.get_rebalance_deltas(allocations, targets)

        trades: list[OrderIntent] = []
        expected_reduction: dict[str, float] = {}

        remaining_cash = snapshot.cash
        estimated_costs = 0.0

        ordered_deltas = sorted(
            deltas.items(),
            key=lambda item: (0 if item[1] > 0 else 1, item[0]),
        )

        for strategy_id, delta_capital in ordered_deltas:
            if strategy_id not in drift:
                continue

            if abs(delta_capital) < self.min_trade_value:
                expected_reduction[strategy_id] = 0.0
                continue

            symbol = self._select_primary_symbol(snapshot.positions, strategy_id)
            if symbol is None:
                expected_reduction[strategy_id] = 0.0
                continue

            price = current_prices.get(symbol)
            if price is None:
                price = self._infer_price(snapshot.positions, strategy_id, symbol)
            if price <= 0:
                expected_reduction[strategy_id] = 0.0
                continue

            executed_capital, order_size = self._calculate_trade_size(
                strategy_id,
                symbol,
                delta_capital,
                price,
                snapshot.positions,
                remaining_cash,
            )

            if order_size <= 0 or executed_capital < self.min_trade_value:
                expected_reduction[strategy_id] = 0.0
                continue

            if delta_capital > 0:
                side: Literal["buy", "sell"] = "buy"
            else:
                side = "sell"

            if side == "buy":
                remaining_cash -= executed_capital
            else:
                remaining_cash += executed_capital

            trades.append(
                self._build_intent(
                    portfolio_id=snapshot.portfolio_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    side=side,
                    qty=order_size,
                    timestamp_ns=snapshot.ts_ns,
                    delta_capital=delta_capital,
                    executed_capital=executed_capital,
                )
            )

            before_abs = abs(drift[strategy_id])
            current = allocations.get(strategy_id, 0.0)
            target = targets.get(strategy_id, 0.0)
            new_current = current + (executed_capital if side == "buy" else -executed_capital)
            after = 0.0
            if target != 0:
                after = abs(((new_current - target) / target) * 100.0)
            expected_reduction[strategy_id] = max(0.0, before_abs - after)

            notional = executed_capital
            trade_cost = notional * (self.commission_rate + self.slippage_rate)
            estimated_costs += trade_cost

        return RebalancePlan(
            portfolio_id=snapshot.portfolio_id,
            timestamp_ns=snapshot.ts_ns,
            trades=trades,
            expected_drift_reduction=expected_reduction,
            estimated_costs=estimated_costs,
        )

    def _compute_current_allocations(
        self,
        positions: Iterable[StrategyPosition],
        current_prices: dict[str, float],
    ) -> dict[str, float]:
        allocations = {alloc.strategy_id: 0.0 for alloc in self.config.enabled_allocations()}

        for pos in positions:
            if pos.strategy_id not in allocations:
                continue
            price = current_prices.get(pos.symbol, pos.current_price)
            allocations[pos.strategy_id] += pos.qty * price

        return allocations

    def _select_primary_symbol(
        self,
        positions: Iterable[StrategyPosition],
        strategy_id: str,
    ) -> str | None:
        best_symbol: str | None = None
        best_notional = 0.0

        for pos in positions:
            if pos.strategy_id != strategy_id:
                continue
            notional = abs(pos.qty * pos.current_price)
            if notional > best_notional:
                best_notional = notional
                best_symbol = pos.symbol

        return best_symbol

    def _infer_price(
        self,
        positions: Iterable[StrategyPosition],
        strategy_id: str,
        symbol: str,
    ) -> float:
        for pos in positions:
            if pos.strategy_id == strategy_id and pos.symbol == symbol:
                return pos.current_price
        return 0.0

    def _calculate_trade_size(
        self,
        strategy_id: str,
        symbol: str,
        delta_capital: float,
        price: float,
        positions: Iterable[StrategyPosition],
        remaining_cash: float,
    ) -> tuple[float, float]:
        target_notional = abs(delta_capital)
        side = "buy" if delta_capital > 0 else "sell"

        if side == "buy":
            available_notional = min(target_notional, max(remaining_cash, 0.0))
            if available_notional <= 0:
                return (0.0, 0.0)
        else:
            available_qty = self._current_quantity(positions, strategy_id, symbol)
            if available_qty <= 0:
                return (0.0, 0.0)
            available_notional = min(target_notional, available_qty * price)

        size = self.sizer.calculate_position_size(
            strategy_id=strategy_id,
            symbol=symbol,
            allocated_capital=available_notional,
            current_price=price,
        )

        if side == "sell":
            size = min(size, self._current_quantity(positions, strategy_id, symbol))

        executed_capital = size * price
        if executed_capital > available_notional + 1e-6:
            executed_capital = available_notional
            size = executed_capital / price

        return (executed_capital, size)

    def _current_quantity(
        self,
        positions: Iterable[StrategyPosition],
        strategy_id: str,
        symbol: str,
    ) -> float:
        return sum(
            pos.qty for pos in positions if pos.strategy_id == strategy_id and pos.symbol == symbol
        )

    def _build_intent(
        self,
        *,
        portfolio_id: str,
        strategy_id: str,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: float,
        timestamp_ns: int,
        delta_capital: float,
        executed_capital: float,
    ) -> OrderIntent:
        intent_id = f"rebalance-{uuid4()}"
        meta = {
            "source": "portfolio_rebalance",
            "portfolio_id": portfolio_id,
            "strategy_id": strategy_id,
            "delta_capital": delta_capital,
            "executed_capital": executed_capital,
        }
        return OrderIntent(
            id=intent_id,
            ts_local_ns=timestamp_ns,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            type="market",
            qty=qty,
            limit_price=None,
            meta=meta,
        )
