"""Backtest runner CLI for executing strategy backtests."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from backtest.contracts import BacktestConfig
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from strategies.registry import StrategyRegistry


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        args: Optional argument list (for testing)

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Run backtest for a strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy ID to backtest",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Symbol to backtest (e.g., ATOM/USDT)",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.001,
        help="Commission rate (default: 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=5.0,
        help="Slippage in basis points (default: 5)",
    )
    parser.add_argument(
        "--journal-dir",
        type=Path,
        default=Path("var/log/njord"),
        help="Journal directory (default: var/log/njord)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/backtest"),
        help="Output directory (default: var/backtest)",
    )

    return parser.parse_args(args)


def parse_date(date_str: str) -> int:
    """Parse date string to epoch nanoseconds.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Epoch nanoseconds

    Raises:
        ValueError: If date format is invalid
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1_000_000_000)
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}': {e}") from e


def format_currency(amount: float) -> str:
    """Format amount as currency.

    Args:
        amount: Dollar amount

    Returns:
        Formatted string
    """
    return f"${amount:,.2f}"


def format_percentage(pct: float) -> str:
    """Format percentage with sign.

    Args:
        pct: Percentage value

    Returns:
        Formatted string
    """
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def print_results(
    strategy_id: str,
    symbol: str,
    start_date: str,
    end_date: str,
    metrics: dict[str, float],
    initial_capital: float,
    final_capital: float,
    num_trades: int,
) -> None:
    """Print backtest results in human-readable format.

    Args:
        strategy_id: Strategy identifier
        symbol: Trading symbol
        start_date: Start date string
        end_date: End date string
        metrics: Performance metrics
        initial_capital: Initial capital
        final_capital: Final capital
        num_trades: Number of trades
    """
    # Calculate days
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end_dt - start_dt).days

    print(f"\nBacktest Results: {strategy_id} on {symbol}")
    print("═" * 51)
    print(f"Period:         {start_date} → {end_date} ({days} days)")
    print(f"Initial:        {format_currency(initial_capital)}")
    print(f"Final:          {format_currency(final_capital)}")
    print(f"Total Return:   {format_percentage(metrics['total_return_pct'])}")
    print(f"Sharpe Ratio:   {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown:   -{metrics['max_drawdown_pct']:.2f}%")
    print(f"Trades:         {num_trades} (win rate: {metrics['win_rate'] * 100:.1f}%)")
    print(f"Profit Factor:  {metrics['profit_factor']:.2f}")
    print()


def save_equity_curve(
    output_dir: Path,
    strategy_id: str,
    symbol: str,
    equity_curve: list[tuple[int, float]],
) -> Path:
    """Save equity curve to NDJSON file.

    Args:
        output_dir: Output directory
        strategy_id: Strategy identifier
        symbol: Trading symbol
        equity_curve: List of (timestamp_ns, equity) tuples

    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create filename
    symbol_clean = symbol.replace("/", "")
    filename = f"equity_{strategy_id}_{symbol_clean}.ndjson"
    output_path = output_dir / filename

    # Write NDJSON
    with output_path.open("w") as f:
        for ts_ns, equity in equity_curve:
            line = json.dumps({"ts_ns": ts_ns, "equity": equity})
            f.write(line + "\n")

    return output_path


def main(args: list[str] | None = None) -> int:
    """Main entry point for backtest runner.

    Args:
        args: Optional argument list (for testing)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        parsed_args = parse_args(args)

        # Parse dates
        start_ts = parse_date(parsed_args.start)
        end_ts = parse_date(parsed_args.end)

        # Validate dates
        if start_ts >= end_ts:
            print("Error: Start date must be before end date", file=sys.stderr)
            return 1

        # Create backtest config
        config = BacktestConfig(
            symbol=parsed_args.symbol,
            strategy_id=parsed_args.strategy,
            start_ts=start_ts,
            end_ts=end_ts,
            initial_capital=parsed_args.capital,
            commission_rate=parsed_args.commission,
            slippage_bps=parsed_args.slippage,
        )

        # Load strategy
        registry = StrategyRegistry()
        registry.discover("strategies.samples")

        try:
            strategy_class = registry.get(parsed_args.strategy)
        except KeyError:
            print(f"Error: Strategy '{parsed_args.strategy}' not found", file=sys.stderr)
            print(f"Available strategies: {list(registry._strategies.keys())}", file=sys.stderr)
            return 1

        # Instantiate strategy
        strategy = strategy_class()

        # Run backtest
        engine = BacktestEngine(
            config=config,
            strategy=strategy,
            journal_dir=parsed_args.journal_dir,
        )

        result = engine.run()

        # Calculate metrics
        metrics = calculate_metrics(
            equity_curve=result.equity_curve,
            trades=engine.trades,
        )

        # Print results
        print_results(
            strategy_id=parsed_args.strategy,
            symbol=parsed_args.symbol,
            start_date=parsed_args.start,
            end_date=parsed_args.end,
            metrics=metrics,
            initial_capital=result.initial_capital,
            final_capital=result.final_capital,
            num_trades=result.num_trades,
        )

        # Save equity curve
        output_path = save_equity_curve(
            output_dir=parsed_args.output_dir,
            strategy_id=parsed_args.strategy,
            symbol=parsed_args.symbol,
            equity_curve=result.equity_curve,
        )

        print(f"Equity curve saved to: {output_path}")
        print()

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
