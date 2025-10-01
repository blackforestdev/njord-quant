"""Portfolio state tracking utilities."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from core.contracts import FillEvent
from portfolio.contracts import (
    PortfolioConfig,
    PortfolioSnapshot,
    StrategyPosition,
)


@dataclass
class _PositionState:
    qty: float = 0.0
    avg_price: float = 0.0
    last_price: float = 0.0


class PortfolioTracker:
    """Track portfolio capital, positions, and performance across strategies."""

    def __init__(
        self,
        config: PortfolioConfig,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or time.time_ns
        self._lock = threading.RLock()

        self._cash_by_strategy: dict[str, float] = {}
        self._positions: dict[str, dict[str, _PositionState]] = {}
        self._realized_pnl_by_strategy: dict[str, float] = {}
        self._total_fees: float = 0.0
        self._last_rebalance_ts: int = 0
        self._last_update_ts: int = 0

        self._initialize_state(config)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def on_fill(self, fill: FillEvent) -> None:
        """Update portfolio state in response to an execution fill."""

        strategy_id = fill.meta.get("strategy_id")
        if strategy_id is None:
            raise ValueError("Fill event meta missing 'strategy_id'")

        if fill.side not in ("buy", "sell"):
            raise ValueError(f"Unsupported fill side '{fill.side}'")

        with self._lock:
            self._ensure_strategy(strategy_id)

            strategy_positions = self._positions[strategy_id]
            state = strategy_positions.setdefault(fill.symbol, _PositionState())

            state.last_price = fill.price

            if fill.side == "buy":
                self._apply_buy(strategy_id, state, fill)
            else:
                self._apply_sell(strategy_id, state, fill)

            self._total_fees += fill.fee
            self._last_update_ts = max(self._last_update_ts, fill.ts_fill_ns)

    def update_mark_to_market(
        self,
        strategy_id: str,
        symbol: str,
        price: float,
        *,
        ts_ns: int | None = None,
    ) -> None:
        """Update the last traded price for a strategy position."""

        if price <= 0:
            raise ValueError("price must be positive")

        with self._lock:
            self._ensure_strategy(strategy_id)
            state = self._positions[strategy_id].setdefault(symbol, _PositionState())
            state.last_price = price
            if ts_ns is not None:
                self._last_update_ts = max(self._last_update_ts, ts_ns)

    def record_rebalance(self, ts_ns: int) -> None:
        """Record the timestamp of the latest rebalance."""

        with self._lock:
            self._last_rebalance_ts = ts_ns
            self._last_update_ts = max(self._last_update_ts, ts_ns)

    def get_last_rebalance_ts(self) -> int:
        """Return timestamp (ns) of last recorded rebalance."""

        with self._lock:
            return self._last_rebalance_ts

    def get_strategy_capital(self, strategy_id: str) -> float:
        """Return current capital (cash + market value) for a strategy."""

        with self._lock:
            self._ensure_strategy(strategy_id)
            return self._strategy_market_value(strategy_id) + self._cash_by_strategy[strategy_id]

    def get_total_equity(self) -> float:
        """Return total portfolio equity."""

        with self._lock:
            cash_total = sum(self._cash_by_strategy.values())
            market_value = sum(
                self._strategy_market_value(strategy_id) for strategy_id in self._cash_by_strategy
            )
            return cash_total + market_value

    def get_snapshot(self) -> PortfolioSnapshot:
        """Build a portfolio snapshot representing the current state."""

        with self._lock:
            ts_ns = self._clock()
            cash_total = sum(self._cash_by_strategy.values())
            positions: list[StrategyPosition] = []

            for strategy_id, position_map in self._positions.items():
                strategy_cash = self._cash_by_strategy[strategy_id]
                for symbol, state in position_map.items():
                    if state.qty == 0 and state.last_price == 0:
                        continue

                    market_value = state.qty * state.last_price
                    allocated_capital = strategy_cash + market_value
                    unrealized = (state.last_price - state.avg_price) * state.qty

                    positions.append(
                        StrategyPosition(
                            strategy_id=strategy_id,
                            symbol=symbol,
                            qty=state.qty,
                            avg_entry_price=state.avg_price,
                            current_price=state.last_price,
                            unrealized_pnl=unrealized,
                            allocated_capital=allocated_capital,
                        )
                    )

            total_equity = cash_total + sum(pos.market_value for pos in positions)

            return PortfolioSnapshot(
                ts_ns=ts_ns,
                portfolio_id=self._config.portfolio_id,
                total_equity=total_equity,
                cash=cash_total,
                positions=positions,
                last_rebalance_ts=self._last_rebalance_ts,
            )

    def get_realized_pnl(self, strategy_id: str) -> float:
        """Return total realized PnL for a strategy."""

        with self._lock:
            self._ensure_strategy(strategy_id)
            return self._realized_pnl_by_strategy[strategy_id]

    def get_total_realized_pnl(self) -> float:
        """Return aggregate realized PnL across all strategies."""

        with self._lock:
            return sum(self._realized_pnl_by_strategy.values())

    def get_total_fees(self) -> float:
        """Return total fees paid across all fills."""

        with self._lock:
            return self._total_fees

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _initialize_state(self, config: PortfolioConfig) -> None:
        enabled_allocs = config.enabled_allocations()
        if not enabled_allocs:
            raise ValueError("PortfolioTracker requires at least one enabled strategy")

        # Allocate cash in proportion to target weights (ensures sum ~= total_capital)
        remaining = config.total_capital
        for alloc in enabled_allocs[:-1]:
            capital = config.total_capital * alloc.target_weight
            self._cash_by_strategy[alloc.strategy_id] = capital
            self._positions[alloc.strategy_id] = {}
            self._realized_pnl_by_strategy[alloc.strategy_id] = 0.0
            remaining -= capital

        last_alloc = enabled_allocs[-1]
        self._cash_by_strategy[last_alloc.strategy_id] = max(remaining, 0.0)
        self._positions[last_alloc.strategy_id] = {}
        self._realized_pnl_by_strategy[last_alloc.strategy_id] = 0.0

    def _ensure_strategy(self, strategy_id: str) -> None:
        if strategy_id in self._cash_by_strategy:
            return

        alloc = self._config.get_allocation(strategy_id)
        if alloc is None or not alloc.enabled:
            raise ValueError(f"Strategy '{strategy_id}' is not enabled in portfolio config")

        self._cash_by_strategy[strategy_id] = 0.0
        self._positions[strategy_id] = {}
        self._realized_pnl_by_strategy[strategy_id] = 0.0

    def _apply_buy(self, strategy_id: str, state: _PositionState, fill: FillEvent) -> None:
        notional = fill.qty * fill.price
        total_cost = state.avg_price * state.qty + notional
        new_qty = state.qty + fill.qty

        state.qty = new_qty
        state.avg_price = total_cost / new_qty if new_qty != 0 else 0.0

        self._cash_by_strategy[strategy_id] -= notional + fill.fee

    def _apply_sell(self, strategy_id: str, state: _PositionState, fill: FillEvent) -> None:
        notional = fill.qty * fill.price
        realized = (fill.price - state.avg_price) * fill.qty

        self._cash_by_strategy[strategy_id] += notional - fill.fee
        self._realized_pnl_by_strategy[strategy_id] += realized - fill.fee

        state.qty -= fill.qty
        if abs(state.qty) < 1e-9:
            state.qty = 0.0
            state.avg_price = 0.0

    def _strategy_market_value(self, strategy_id: str) -> float:
        position_map = self._positions.get(strategy_id, {})
        return sum(state.qty * state.last_price for state in position_map.values())
