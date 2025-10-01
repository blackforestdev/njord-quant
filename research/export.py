"""Data export utilities for research analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pandas as pd

    from backtest.contracts import BacktestResult
    from research.data_reader import DataReader
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]

    try:
        from backtest.contracts import BacktestResult
    except ImportError:
        BacktestResult = None  # type: ignore[assignment,misc]

    try:
        from research.data_reader import DataReader
    except ImportError:
        DataReader = None  # type: ignore[assignment,misc]


class DataExporter:
    """Export data to various formats for external tools."""

    def __init__(self, data_reader: DataReader) -> None:
        if pd is None:
            raise ImportError("pandas is required for DataExporter")
        self.data_reader = data_reader

    def export_ohlcv_to_csv(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        output_path: Path | str,
    ) -> None:
        """Export OHLCV to CSV.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1m", "1h", "1d")
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            output_path: Output CSV file path
        """
        df = self.data_reader.read_ohlcv(
            symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        )

        if df.empty:
            # Create empty CSV with headers
            df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        else:
            # Convert ts_open to timestamp column
            if "ts_open" in df.columns:
                df["timestamp"] = pd.to_datetime(df["ts_open"], unit="ns")
                # Reorder columns
                cols = ["timestamp", "open", "high", "low", "close", "volume"]
                df = df[[c for c in cols if c in df.columns]]

        # Export to CSV
        df.to_csv(output_path, index=False, date_format="%Y-%m-%d %H:%M:%S")

    def export_ohlcv_to_parquet(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        output_path: Path | str,
        *,
        compression: Literal["snappy", "gzip", "none"] = "snappy",
    ) -> None:
        """Export OHLCV to Parquet.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1m", "1h", "1d")
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            output_path: Output Parquet file path
            compression: Compression algorithm ("snappy", "gzip", "none")
        """
        df = self.data_reader.read_ohlcv(
            symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        )

        if df.empty:
            # Create empty DataFrame with proper schema
            df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        else:
            # Convert ts_open to timestamp column
            if "ts_open" in df.columns:
                df["timestamp"] = pd.to_datetime(df["ts_open"], unit="ns")
                # Reorder columns
                cols = ["timestamp", "open", "high", "low", "close", "volume"]
                df = df[[c for c in cols if c in df.columns]]

        # Export to Parquet
        compression_arg = None if compression == "none" else compression
        df.to_parquet(output_path, compression=compression_arg, index=False)

    def export_backtest_results_to_json(
        self,
        results: dict[str, BacktestResult],
        output_path: Path | str,
        *,
        indent: int | None = 2,
    ) -> None:
        """Export backtest results to JSON.

        Args:
            results: Dict mapping strategy_id to BacktestResult
            output_path: Output JSON file path
            indent: JSON indentation (None for compact)
        """
        json_data: dict[str, Any] = {}

        for strategy_id, result in results.items():
            json_data[strategy_id] = {
                "strategy_id": result.strategy_id,
                "symbol": result.symbol,
                "start_ts": result.start_ts,
                "end_ts": result.end_ts,
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
                "total_return_pct": result.total_return_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
                "win_rate": result.win_rate if hasattr(result, "win_rate") else None,
                "profit_factor": result.profit_factor if hasattr(result, "profit_factor") else None,
                "num_trades": result.num_trades,
                "equity_curve": [{"timestamp": ts, "equity": eq} for ts, eq in result.equity_curve],
            }

        # Write to JSON file
        output_path = Path(output_path)
        with output_path.open("w") as f:
            json.dump(json_data, f, indent=indent)

    def export_fills_to_csv(
        self,
        strategy_id: str | None,
        start_ts: int,
        end_ts: int,
        output_path: Path | str,
    ) -> None:
        """Export fill events to CSV.

        Args:
            strategy_id: Strategy ID to filter (None for all strategies)
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            output_path: Output CSV file path
        """
        df = self.data_reader.read_fills(strategy_id=strategy_id, start_ts=start_ts, end_ts=end_ts)

        if df.empty:
            # Create empty CSV with headers
            df = pd.DataFrame(
                columns=[
                    "ts_fill_ns",
                    "strategy_id",
                    "symbol",
                    "side",
                    "qty",
                    "price",
                    "fee",
                    "realized_pnl",
                ]
            )

        # Convert timestamp to datetime if present
        if "ts_fill_ns" in df.columns and not df.empty:
            df["timestamp"] = pd.to_datetime(df["ts_fill_ns"], unit="ns")
            # Reorder columns to put timestamp first
            cols = ["timestamp"] + [c for c in df.columns if c != "timestamp"]
            df = df[cols]

        # Export to CSV
        df.to_csv(output_path, index=False, date_format="%Y-%m-%d %H:%M:%S")

    def export_positions_to_csv(
        self,
        portfolio_id: str,
        start_ts: int,
        end_ts: int,
        output_path: Path | str,
    ) -> None:
        """Export position snapshots to CSV.

        Args:
            portfolio_id: Portfolio ID to filter
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            output_path: Output CSV file path
        """
        df = self.data_reader.read_positions(
            portfolio_id=portfolio_id, start_ts=start_ts, end_ts=end_ts
        )

        if df.empty:
            # Create empty CSV with headers
            df = pd.DataFrame(
                columns=[
                    "ts_ns",
                    "strategy_id",
                    "symbol",
                    "qty",
                    "avg_entry_price",
                    "unrealized_pnl",
                    "total_equity",
                ]
            )

        # Convert timestamp to datetime if present
        if "ts_ns" in df.columns and not df.empty:
            df["timestamp"] = pd.to_datetime(df["ts_ns"], unit="ns")
            # Reorder columns to put timestamp first
            cols = ["timestamp"] + [c for c in df.columns if c != "timestamp"]
            df = df[cols]

        # Export to CSV
        df.to_csv(output_path, index=False, date_format="%Y-%m-%d %H:%M:%S")

    def export_equity_curve_to_json(
        self,
        result: BacktestResult,
        output_path: Path | str,
        *,
        indent: int | None = 2,
    ) -> None:
        """Export equity curve to JSON for web visualization.

        Args:
            result: BacktestResult to export
            output_path: Output JSON file path
            indent: JSON indentation (None for compact)
        """
        json_data = {
            "strategy_id": result.strategy_id,
            "symbol": result.symbol,
            "metrics": {
                "total_return_pct": result.total_return_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
                "num_trades": result.num_trades,
            },
            "equity_curve": [{"timestamp": ts, "equity": eq} for ts, eq in result.equity_curve],
        }

        # Write to JSON file
        output_path = Path(output_path)
        with output_path.open("w") as f:
            json.dump(json_data, f, indent=indent)
