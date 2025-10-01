"""Performance metrics calculation for backtests."""

from __future__ import annotations


def calculate_metrics(
    equity_curve: list[tuple[int, float]],
    trades: list[dict[str, object]] | None = None,
) -> dict[str, float]:
    """Calculate backtest performance metrics.

    Args:
        equity_curve: List of (timestamp_ns, equity) tuples
        trades: Optional list of trade dicts with 'side', 'qty', 'price', 'commission'

    Returns:
        Dictionary of performance metrics
    """
    if not equity_curve:
        return _empty_metrics()

    initial_capital = equity_curve[0][1]
    final_capital = equity_curve[-1][1]

    # Calculate basic metrics
    total_return_pct = (
        ((final_capital - initial_capital) / initial_capital) * 100.0
        if initial_capital > 0
        else 0.0
    )

    # Calculate Sharpe ratio (annualized)
    sharpe_ratio = _calculate_sharpe_ratio(equity_curve)

    # Calculate max drawdown
    max_drawdown_pct, max_drawdown_duration_days = _calculate_max_drawdown(equity_curve)

    # Calculate volatility (annualized)
    volatility_annual_pct = _calculate_volatility(equity_curve)

    # Calculate Calmar ratio
    calmar_ratio = total_return_pct / max_drawdown_pct if max_drawdown_pct > 0 else 0.0

    # Calculate trade statistics
    trade_stats = _calculate_trade_stats(trades) if trades else {}

    return {
        "total_return_pct": total_return_pct,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_duration_days": max_drawdown_duration_days,
        "volatility_annual_pct": volatility_annual_pct,
        "calmar_ratio": calmar_ratio,
        "win_rate": trade_stats.get("win_rate", 0.0),
        "profit_factor": trade_stats.get("profit_factor", 0.0),
        "avg_win": trade_stats.get("avg_win", 0.0),
        "avg_loss": trade_stats.get("avg_loss", 0.0),
        "largest_win": trade_stats.get("largest_win", 0.0),
        "largest_loss": trade_stats.get("largest_loss", 0.0),
    }


def _empty_metrics() -> dict[str, float]:
    """Return metrics for empty equity curve."""
    return {
        "total_return_pct": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "max_drawdown_duration_days": 0.0,
        "volatility_annual_pct": 0.0,
        "calmar_ratio": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
    }


def _calculate_sharpe_ratio(equity_curve: list[tuple[int, float]]) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        equity_curve: List of (timestamp_ns, equity) tuples

    Returns:
        Annualized Sharpe ratio
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate returns
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1][1]
        curr_equity = equity_curve[i][1]
        ret = (curr_equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
        returns.append(ret)

    if not returns:
        return 0.0

    # Calculate mean and std
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = variance**0.5

    if std_return == 0:
        return 0.0

    # Annualize (assuming daily returns, 365 days per year)
    sharpe = (mean_return / std_return) * (365**0.5)
    return float(sharpe)


def _calculate_max_drawdown(
    equity_curve: list[tuple[int, float]],
) -> tuple[float, float]:
    """Calculate maximum drawdown and duration.

    Args:
        equity_curve: List of (timestamp_ns, equity) tuples

    Returns:
        Tuple of (max_drawdown_pct, max_drawdown_duration_days)
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0

    max_drawdown = 0.0
    peak = equity_curve[0][1]
    peak_ts = equity_curve[0][0]
    max_drawdown_duration_ns = 0

    drawdown_start_ts = 0
    in_drawdown = False

    for ts, equity in equity_curve:
        if equity > peak:
            # New peak
            peak = equity
            peak_ts = ts
            in_drawdown = False
        else:
            # In drawdown
            if not in_drawdown:
                drawdown_start_ts = peak_ts
                in_drawdown = True

            drawdown = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)

            # Update max duration
            if in_drawdown:
                duration_ns = ts - drawdown_start_ts
                max_drawdown_duration_ns = max(max_drawdown_duration_ns, duration_ns)

    # Convert nanoseconds to days
    max_drawdown_duration_days = max_drawdown_duration_ns / (1_000_000_000 * 60 * 60 * 24)

    return max_drawdown, max_drawdown_duration_days


def _calculate_volatility(equity_curve: list[tuple[int, float]]) -> float:
    """Calculate annualized volatility.

    Args:
        equity_curve: List of (timestamp_ns, equity) tuples

    Returns:
        Annualized volatility as percentage
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate returns
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1][1]
        curr_equity = equity_curve[i][1]
        ret = (curr_equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
        returns.append(ret)

    if not returns:
        return 0.0

    # Calculate std deviation
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = variance**0.5

    # Annualize (assuming daily returns)
    volatility_annual = std_return * (365**0.5) * 100.0
    return float(volatility_annual)


def _calculate_trade_stats(trades: list[dict[str, object]]) -> dict[str, float]:
    """Calculate trade-level statistics.

    Args:
        trades: List of trade dicts with 'side', 'qty', 'price', 'commission'

    Returns:
        Dictionary of trade statistics
    """
    if len(trades) < 2:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
        }

    # Pair buy/sell trades to calculate PnL
    pnls: list[float] = []
    buy_price = None
    buy_qty = 0.0

    for trade in trades:
        side = trade.get("side")
        price = float(trade.get("price", 0.0))  # type: ignore[arg-type]
        qty = float(trade.get("qty", 0.0))  # type: ignore[arg-type]

        if side == "buy":
            buy_price = price
            buy_qty = qty
        elif side == "sell" and buy_price is not None:
            sell_price = price
            sell_qty = qty
            pnl = (sell_price - buy_price) * min(buy_qty, sell_qty)
            pnls.append(pnl)
            buy_price = None

    if not pnls:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
        }

    # Calculate statistics
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / len(pnls) if pnls else 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    largest_win = max(wins) if wins else 0.0
    largest_loss = min(losses) if losses else 0.0

    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
    }
