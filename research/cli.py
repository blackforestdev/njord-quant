"""Command-line interface for research operations."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from research.data_reader import DataReader
    from research.export import DataExporter
    from research.validator import DataValidator
except ImportError as e:
    print(f"Error importing research modules: {e}", file=sys.stderr)
    sys.exit(1)


def parse_timestamp(date_str: str) -> int:
    """Parse date string to nanosecond timestamp.

    Args:
        date_str: Date string in format YYYY-MM-DD

    Returns:
        Timestamp in nanoseconds (UTC)
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def export_ohlcv(args: argparse.Namespace) -> int:
    """Export OHLCV data to file.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        reader = DataReader(args.journal_dir)
        exporter = DataExporter(reader)

        start_ts = parse_timestamp(args.start)
        end_ts = parse_timestamp(args.end)

        print(f"Exporting {args.symbol} {args.timeframe} from {args.start} to {args.end}...")

        if args.format == "csv":
            exporter.export_ohlcv_to_csv(
                symbol=args.symbol,
                timeframe=args.timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                output_path=args.output,
            )
        elif args.format == "parquet":
            exporter.export_ohlcv_to_parquet(
                symbol=args.symbol,
                timeframe=args.timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                output_path=args.output,
                compression=args.compression,
            )
        else:
            print(f"Unsupported format: {args.format}", file=sys.stderr)
            return 1

        print(f"Exported to {args.output}")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def validate_data(args: argparse.Namespace) -> int:
    """Validate data quality.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        reader = DataReader(args.journal_dir)
        validator = DataValidator(reader)

        start_ts = parse_timestamp(args.start)
        end_ts = parse_timestamp(args.end)

        print(f"Validating {args.symbol} {args.timeframe} from {args.start} to {args.end}...")

        report = validator.generate_quality_report(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        # Print report
        print("\n=== Data Quality Report ===")
        print(f"Symbol: {report['symbol']}")
        print(f"Timeframe: {report['timeframe']}")
        print(f"Total bars: {report['total_bars']}")

        if report["total_bars"] > 0:
            print(f"\nGaps: {report['summary']['total_gaps']}")
            print(f"Spikes: {report['summary']['total_spikes']}")
            print(f"Flatlines: {report['summary']['total_flatlines']}")
            print(f"Consistency issues: {report['summary']['total_consistency_issues']}")
            print(f"\nQuality score: {report['summary']['quality_score']:.1f}/100")
        else:
            print("\nNo data found in specified range")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nDetailed report saved to {args.output}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def list_data(args: argparse.Namespace) -> int:
    """List available data.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        journal_dir = Path(args.journal_dir)

        if not journal_dir.exists():
            print(f"Journal directory not found: {journal_dir}", file=sys.stderr)
            return 1

        # Find OHLCV files
        ohlcv_files = list(journal_dir.glob("ohlcv.*.ndjson*"))

        if not ohlcv_files:
            print("No OHLCV data found")
            return 0

        print("=== Available OHLCV Data ===\n")

        # Parse file names to extract symbol and timeframe
        data_map: dict[str, set[str]] = {}
        for file in ohlcv_files:
            # Pattern: ohlcv.{timeframe}.{symbol}.ndjson
            parts = file.stem.split(".")
            if len(parts) >= 3:
                timeframe = parts[1]
                symbol = parts[2]
                # Convert ATOMUSDT back to ATOM/USDT
                if len(symbol) >= 4:
                    symbol = f"{symbol[:-4]}/{symbol[-4:]}"

                if symbol not in data_map:
                    data_map[symbol] = set()
                data_map[symbol].add(timeframe)

        # Print organized by symbol
        for symbol in sorted(data_map.keys()):
            timeframes = sorted(data_map[symbol])
            print(f"{symbol}: {', '.join(timeframes)}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def compare_backtests(args: argparse.Namespace) -> int:
    """Compare backtest results.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        from backtest.contracts import BacktestResult
        from research.comparison import StrategyComparison

        # Load backtest results
        results: dict[str, BacktestResult] = {}

        for result_file in args.results:
            with open(result_file) as f:
                data = json.load(f)

            # Handle both single result and dict of results
            if isinstance(data, dict):
                for strategy_id, result_data in data.items():
                    if isinstance(result_data, dict) and "strategy_id" in result_data:
                        # Convert equity curve from dict format to tuple format
                        equity_curve = [
                            (int(item["timestamp"]), float(item["equity"]))
                            for item in result_data.get("equity_curve", [])
                        ]

                        results[strategy_id] = BacktestResult(
                            strategy_id=result_data["strategy_id"],
                            symbol=result_data["symbol"],
                            start_ts=result_data["start_ts"],
                            end_ts=result_data["end_ts"],
                            initial_capital=result_data["initial_capital"],
                            final_capital=result_data["final_capital"],
                            total_return_pct=result_data["total_return_pct"],
                            sharpe_ratio=result_data["sharpe_ratio"],
                            max_drawdown_pct=result_data["max_drawdown_pct"],
                            win_rate=result_data.get("win_rate", 0.0),
                            profit_factor=result_data.get("profit_factor", 0.0),
                            num_trades=result_data["num_trades"],
                            equity_curve=equity_curve,
                        )

        if len(results) < 2:
            print("Need at least 2 backtest results to compare", file=sys.stderr)
            return 1

        print(f"Comparing {len(results)} strategies...")

        # Compare strategies
        comparison = StrategyComparison(results)
        metrics_df = comparison.compare_metrics()

        print("\n=== Strategy Comparison ===\n")
        print(metrics_df.to_string())

        if args.output:
            metrics_df.to_csv(args.output)
            print(f"\nComparison saved to {args.output}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(
        description="Research CLI for data analysis and export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Export OHLCV command
    export_parser = subparsers.add_parser("export-ohlcv", help="Export OHLCV data")
    export_parser.add_argument("--symbol", required=True, help="Trading symbol (e.g., ATOM/USDT)")
    export_parser.add_argument("--timeframe", required=True, help="Timeframe (e.g., 1m, 1h, 1d)")
    export_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    export_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    export_parser.add_argument(
        "--format", choices=["csv", "parquet"], default="csv", help="Output format"
    )
    export_parser.add_argument(
        "--compression",
        choices=["snappy", "gzip", "none"],
        default="snappy",
        help="Compression for Parquet",
    )
    export_parser.add_argument("--output", required=True, help="Output file path")
    export_parser.add_argument(
        "--journal-dir", default="var/journals", help="Journal directory path"
    )

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate data quality")
    validate_parser.add_argument("--symbol", required=True, help="Trading symbol (e.g., ATOM/USDT)")
    validate_parser.add_argument("--timeframe", required=True, help="Timeframe (e.g., 1m, 1h, 1d)")
    validate_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    validate_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    validate_parser.add_argument("--output", help="Save detailed report to JSON file")
    validate_parser.add_argument(
        "--journal-dir", default="var/journals", help="Journal directory path"
    )

    # List data command
    list_parser = subparsers.add_parser("list-data", help="List available data")
    list_parser.add_argument("--journal-dir", default="var/journals", help="Journal directory path")

    # Compare backtests command
    compare_parser = subparsers.add_parser("compare-backtests", help="Compare backtest results")
    compare_parser.add_argument(
        "--results", action="append", required=True, help="Backtest result JSON files"
    )
    compare_parser.add_argument("--output", help="Output CSV file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to appropriate handler
    if args.command == "export-ohlcv":
        return export_ohlcv(args)
    elif args.command == "validate":
        return validate_data(args)
    elif args.command == "list-data":
        return list_data(args)
    elif args.command == "compare-backtests":
        return compare_backtests(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
