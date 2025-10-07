"""Execution performance tracking and analysis.

This module provides tools for analyzing execution quality, calculating
implementation shortfall, comparing to benchmarks, and scoring venue performance.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Literal

from execution.contracts import ExecutionReport
from research.data_reader import DataReader


class ExecutionPerformanceTracker:
    """Track and analyze execution quality metrics.

    Provides tools for:
    - Implementation shortfall analysis (market impact, timing cost, fees)
    - Benchmark comparisons (arrival, VWAP, TWAP)
    - Algorithm performance aggregation
    - Venue quality scoring

    Attributes:
        data_reader: DataReader instance for accessing historical market data
    """

    def __init__(self, data_reader: DataReader) -> None:
        """Initialize performance tracker.

        Args:
            data_reader: DataReader instance for market data access
        """
        self.data_reader = data_reader

    def calculate_implementation_shortfall(
        self,
        report: ExecutionReport,
        arrival_price: float,
    ) -> dict[str, float]:
        """Calculate implementation shortfall decomposition.

        Implementation shortfall is the difference between execution price
        and arrival price, decomposed into:
        - Market impact: Price movement due to order execution
        - Timing cost: Opportunity cost from delayed execution
        - Fees: Transaction costs

        Args:
            report: ExecutionReport with execution results
            arrival_price: Arrival (reference) price at decision time

        Returns:
            Dictionary with shortfall components in basis points:
            {
                "total_shortfall_bps": float,
                "market_impact_bps": float,
                "timing_cost_bps": float,
                "fees_bps": float
            }

        Note:
            Positive values indicate worse performance (higher costs).
            For sell orders, price impact is inverted (lower price = worse).
        """
        if arrival_price <= 0:
            raise ValueError("arrival_price must be > 0")

        # Handle edge case: no fills
        if report.filled_quantity == 0:
            return {
                "total_shortfall_bps": 0.0,
                "market_impact_bps": 0.0,
                "timing_cost_bps": 0.0,
                "fees_bps": 0.0,
            }

        # Calculate price difference (avg fill price vs arrival price)
        price_diff = report.avg_fill_price - arrival_price

        # For sell orders, lower price is worse (invert sign)
        # For buy orders, higher price is worse (keep sign)
        # Normalize by arrival price and convert to basis points
        total_shortfall_bps = (price_diff / arrival_price) * 10000

        # Fee component (always positive cost)
        # Use avg_fill_price for accurate notional calculation
        fees_bps = (report.total_fees / (report.filled_quantity * report.avg_fill_price)) * 10000

        # Simplified decomposition:
        # - Timing cost: Use benchmark VWAP deviation if available
        # - Market impact: Remainder after timing cost
        # Note: fees_bps is tracked separately from price-based shortfall
        if report.vwap_deviation is not None:
            # VWAP deviation represents timing cost (deviation from market VWAP)
            timing_cost_bps = report.vwap_deviation * 10000
            market_impact_bps = total_shortfall_bps - timing_cost_bps
        else:
            # Without VWAP benchmark, estimate 50/50 split between market impact and timing
            market_impact_bps = total_shortfall_bps * 0.5
            timing_cost_bps = total_shortfall_bps * 0.5

        return {
            "total_shortfall_bps": total_shortfall_bps,
            "market_impact_bps": market_impact_bps,
            "timing_cost_bps": timing_cost_bps,
            "fees_bps": fees_bps,
        }

    def compare_to_benchmark(
        self,
        report: ExecutionReport,
        benchmark: Literal["arrival", "vwap", "twap"],
    ) -> float:
        """Compare execution to benchmark price.

        Calculates the difference between average fill price and benchmark,
        expressed in basis points. Positive values indicate worse performance.

        Args:
            report: ExecutionReport with execution results
            benchmark: Benchmark type (arrival, vwap, twap)

        Returns:
            Difference in basis points (positive = worse than benchmark)

        Raises:
            ValueError: If benchmark is "vwap" but report lacks benchmark_vwap
            ValueError: If benchmark is "arrival" but report lacks arrival_price
        """
        # Handle edge case: no fills
        if report.filled_quantity == 0:
            return 0.0

        # Get benchmark price
        if benchmark == "arrival":
            if report.arrival_price is None:
                raise ValueError("ExecutionReport missing arrival_price for arrival benchmark")
            benchmark_price = report.arrival_price

        elif benchmark == "vwap":
            if report.benchmark_vwap is None:
                raise ValueError("ExecutionReport missing benchmark_vwap for vwap benchmark")
            benchmark_price = report.benchmark_vwap

        elif benchmark == "twap":
            # TWAP benchmark is average fill price over execution period
            # For simplicity, use arrival price as TWAP estimate
            # TODO(future): Calculate actual TWAP from market data via DataReader
            if report.arrival_price is None:
                raise ValueError("ExecutionReport missing arrival_price for twap benchmark")
            benchmark_price = report.arrival_price

        else:
            raise ValueError(f"Unknown benchmark: {benchmark!r}")

        if benchmark_price <= 0:
            raise ValueError("benchmark price must be > 0")

        price_diff = report.avg_fill_price - benchmark_price
        deviation_bps = (price_diff / benchmark_price) * 10000

        return deviation_bps

    def analyze_algorithm_performance(
        self,
        reports: list[ExecutionReport],
    ) -> Any:
        """Analyze performance metrics across multiple executions.

        Aggregates execution metrics by algorithm type and venue, computing
        average fill prices, slippage, fees, and fill rates.

        Args:
            reports: List of ExecutionReport instances to analyze

        Returns:
            pandas DataFrame with columns:
            - algorithm: Algorithm type (TWAP, VWAP, Iceberg, POV)
            - executions: Number of executions
            - avg_fill_price: Average fill price across executions
            - avg_slippage_bps: Average slippage vs arrival price (basis points)
            - avg_fees_bps: Average fees (basis points)
            - fill_rate: Percentage of orders filled (filled_qty / total_qty)
            - total_volume: Total volume executed

        Note:
            Requires pandas to be installed (optional dependency from Phase 7).
            Returns empty DataFrame if pandas not available.
        """
        try:
            import pandas as pd
        except ModuleNotFoundError:
            # Pandas not available - return empty DataFrame-like structure
            # This allows graceful degradation in environments without pandas
            return []

        # Handle edge case: no reports
        if not reports:
            return pd.DataFrame(
                columns=[
                    "algorithm",
                    "executions",
                    "avg_fill_price",
                    "avg_slippage_bps",
                    "avg_fees_bps",
                    "fill_rate",
                    "total_volume",
                ]
            )

        # Build records for DataFrame
        records: list[dict[str, Any]] = []

        # Group by algorithm (extract from execution_id prefix or use symbol as fallback)
        algo_groups: dict[str, list[ExecutionReport]] = {}

        for report in reports:
            # Extract algorithm from execution_id (format: "algo_xxxxx")
            algo = report.execution_id.split("_")[0].upper()
            if algo not in algo_groups:
                algo_groups[algo] = []
            algo_groups[algo].append(report)

        # Calculate metrics per algorithm
        for algo, algo_reports in algo_groups.items():
            total_filled = sum(r.filled_quantity for r in algo_reports)
            total_target = sum(r.total_quantity for r in algo_reports)

            # Skip if no fills
            if total_filled == 0:
                continue

            # Weighted average fill price (by filled quantity)
            avg_fill_price = (
                sum(r.avg_fill_price * r.filled_quantity for r in algo_reports) / total_filled
            )

            # Average slippage (use arrival_price if available)
            slippages = []
            for r in algo_reports:
                if r.arrival_price is not None and r.filled_quantity > 0:
                    slippage_bps = ((r.avg_fill_price - r.arrival_price) / r.arrival_price) * 10000
                    slippages.append(slippage_bps)
            avg_slippage_bps = sum(slippages) / len(slippages) if slippages else 0.0

            # Average fees (basis points of notional)
            total_fees = sum(r.total_fees for r in algo_reports)
            avg_fees_bps = (total_fees / (total_filled * avg_fill_price)) * 10000

            # Fill rate
            fill_rate = (total_filled / total_target) * 100 if total_target > 0 else 0.0

            records.append(
                {
                    "algorithm": algo,
                    "executions": len(algo_reports),
                    "avg_fill_price": avg_fill_price,
                    "avg_slippage_bps": avg_slippage_bps,
                    "avg_fees_bps": avg_fees_bps,
                    "fill_rate": fill_rate,
                    "total_volume": total_filled,
                }
            )

        return pd.DataFrame(records)

    def score_venue_quality(
        self,
        venue: str,
        symbol: str,
        lookback_days: int = 30,
    ) -> dict[str, float]:
        """Score venue execution quality.

        Analyzes historical fills for the given venue and symbol to compute
        quality metrics.

        Args:
            venue: Venue identifier (e.g., "binanceus", "coinbase")
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            lookback_days: Number of days to look back for analysis

        Returns:
            Dictionary with venue quality metrics:
            {
                "avg_slippage_bps": float,
                "fill_rate": float,
                "avg_latency_ms": float
            }

        Note:
            Current implementation returns placeholder values.
            TODO(future): Integrate with DataReader to compute from historical fills
        """
        end_ts = int(time.time_ns())
        start_ts = end_ts - int(lookback_days * 24 * 60 * 60 * 1_000_000_000)

        fills = self.data_reader.read_fills(
            strategy_id=None,
            start_ts=start_ts,
            end_ts=end_ts,
            format="pandas",
        )

        try:
            import pandas as pd
        except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
            return {"avg_slippage_bps": 0.0, "fill_rate": 0.0, "avg_latency_ms": 0.0}

        if fills is None:
            return {"avg_slippage_bps": 0.0, "fill_rate": 0.0, "avg_latency_ms": 0.0}

        df = pd.DataFrame(fills)
        if df.empty:
            return {"avg_slippage_bps": 0.0, "fill_rate": 0.0, "avg_latency_ms": 0.0}

        def _meta_value(meta: Any, key: str) -> Any:
            if isinstance(meta, Mapping):
                return meta.get(key)
            return None

        df = df.copy()
        df["venue"] = df["meta"].apply(lambda m: _meta_value(m, "venue"))
        df["arrival_price"] = df["meta"].apply(lambda m: _meta_value(m, "arrival_price"))
        df["requested_qty"] = df["meta"].apply(lambda m: _meta_value(m, "requested_qty"))
        df["ts_order_ns"] = df["meta"].apply(lambda m: _meta_value(m, "ts_order_ns"))

        df = df[(df["symbol"] == symbol) & (df["venue"] == venue)]
        if df.empty:
            return {"avg_slippage_bps": 0.0, "fill_rate": 0.0, "avg_latency_ms": 0.0}

        # Slippage calculation (only when arrival price available and positive)
        slippage_rows = df.dropna(subset=["arrival_price"])
        if not slippage_rows.empty:
            valid_arrival = slippage_rows["arrival_price"].astype(float) > 0
            slippage_rows = slippage_rows[valid_arrival]
        if not slippage_rows.empty:
            slippage_bps = (
                (
                    slippage_rows["price"].astype(float)
                    - slippage_rows["arrival_price"].astype(float)
                )
                / slippage_rows["arrival_price"].astype(float)
            ) * 10000
            avg_slippage_bps = float(slippage_bps.mean())
        else:
            avg_slippage_bps = 0.0

        # Fill rate
        filled_qty = float(df["qty"].astype(float).sum())
        requested_series = df["requested_qty"].astype(float, errors="ignore")
        if requested_series.dtype == "object":
            requested_series = requested_series.apply(lambda v: float(v) if v is not None else None)
        requested_qty = requested_series.fillna(df["qty"].astype(float)).sum()
        fill_rate = float((filled_qty / requested_qty) * 100) if requested_qty else 100.0

        # Latency in milliseconds
        latency_rows = df.dropna(subset=["ts_order_ns"])
        if not latency_rows.empty:
            latencies_ms = (
                latency_rows["ts_fill_ns"].astype(float) - latency_rows["ts_order_ns"].astype(float)
            ) / 1_000_000
            avg_latency_ms = float(latencies_ms.mean())
        else:
            avg_latency_ms = 0.0

        return {
            "avg_slippage_bps": avg_slippage_bps,
            "fill_rate": fill_rate,
            "avg_latency_ms": avg_latency_ms,
        }
