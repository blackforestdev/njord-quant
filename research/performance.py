"""Performance analytics for research analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]


class PerformanceAnalyzer:
    """Calculate research-focused performance metrics."""

    def __init__(self, fills_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
        if pd is None:
            raise ImportError("pandas is required for PerformanceAnalyzer")
        self.fills_df = fills_df
        self.positions_df = positions_df

    def calculate_pnl_timeseries(
        self,
        *,
        resample_freq: str = "1D",
    ) -> pd.DataFrame:
        """Calculate PnL time series (daily, hourly, etc.).

        Args:
            resample_freq: Resampling frequency (e.g., "1D", "1H")

        Returns:
            DataFrame with datetime index and pnl column
        """
        if self.fills_df.empty:
            return pd.DataFrame(columns=["pnl"])

        # Ensure fills have timestamp column
        df = self.fills_df.copy()
        if "ts_fill_ns" in df.columns and "timestamp" not in df.columns:
            df["timestamp"] = pd.to_datetime(df["ts_fill_ns"], unit="ns")
        elif "timestamp" in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
                df["timestamp"] = pd.to_datetime(df["timestamp"])
        else:
            raise ValueError("fills_df must have 'ts_fill_ns' or 'timestamp' column")

        df = df.set_index("timestamp")

        # Calculate realized PnL per fill
        if "realized_pnl" not in df.columns:
            # Estimate from price * qty if realized_pnl not available
            if "price" in df.columns and "qty" in df.columns:
                df["realized_pnl"] = df["price"] * df["qty"]
            else:
                df["realized_pnl"] = 0.0

        # Resample and sum PnL
        pnl_series = df["realized_pnl"].resample(resample_freq).sum()
        result = pd.DataFrame({"pnl": pnl_series})

        return result

    def analyze_drawdowns(self) -> pd.DataFrame:
        """Return DataFrame of drawdown periods with duration and recovery time.

        Returns:
            DataFrame with columns: start, end, depth_pct, duration_days, recovery_days
        """
        if self.positions_df.empty:
            return pd.DataFrame(
                columns=["start", "end", "depth_pct", "duration_days", "recovery_days"]
            )

        # Get equity curve from positions
        df = self.positions_df.copy()
        if "ts_ns" in df.columns:
            df["timestamp"] = pd.to_datetime(df["ts_ns"], unit="ns")
        elif "timestamp" not in df.columns:
            raise ValueError("positions_df must have 'ts_ns' or 'timestamp' column")

        df = df.sort_values("timestamp")

        if "total_equity" not in df.columns:
            raise ValueError("positions_df must have 'total_equity' column")

        equity = df["total_equity"].values
        timestamps = pd.to_datetime(df["timestamp"])

        # Find all drawdown periods
        drawdowns = []
        running_max = equity[0]
        dd_start_idx = None

        for i, eq in enumerate(equity):
            if eq > running_max:
                # End of drawdown
                if dd_start_idx is not None:
                    # Convert to ndarray and use numpy min() to avoid type issues
                    import numpy as np

                    dd_slice = np.asarray(equity[dd_start_idx:i])
                    min_value = float(np.min(dd_slice)) if len(dd_slice) > 0 else running_max
                    depth = (running_max - min_value) / running_max * 100
                    drawdowns.append(
                        {
                            "start": timestamps.iloc[dd_start_idx],
                            "end": timestamps.iloc[i - 1],
                            "depth_pct": depth,
                            "duration_days": (
                                timestamps.iloc[i - 1] - timestamps.iloc[dd_start_idx]
                            ).total_seconds()
                            / 86400,
                            "recovery_days": (
                                timestamps.iloc[i] - timestamps.iloc[i - 1]
                            ).total_seconds()
                            / 86400,
                        }
                    )
                    dd_start_idx = None
                running_max = eq
            elif eq < running_max and dd_start_idx is None:
                dd_start_idx = i

        # Handle open drawdown
        if dd_start_idx is not None:
            import numpy as np

            dd_slice = np.asarray(equity[dd_start_idx:])
            min_value = float(np.min(dd_slice)) if len(dd_slice) > 0 else running_max
            depth = (running_max - min_value) / running_max * 100
            drawdowns.append(
                {
                    "start": timestamps.iloc[dd_start_idx],
                    "end": timestamps.iloc[-1],
                    "depth_pct": depth,
                    "duration_days": (
                        timestamps.iloc[-1] - timestamps.iloc[dd_start_idx]
                    ).total_seconds()
                    / 86400,
                    "recovery_days": 0.0,  # Not recovered yet
                }
            )

        return pd.DataFrame(drawdowns)

    def analyze_trade_distribution(self) -> dict[str, Any]:
        """Return statistics on trade sizes, durations, PnL distribution.

        Returns:
            Dict with keys: count, avg_size, avg_pnl, pnl_percentiles, win_rate
        """
        if self.fills_df.empty:
            return {
                "count": 0,
                "avg_size": 0.0,
                "avg_pnl": 0.0,
                "pnl_percentiles": {"25%": 0.0, "50%": 0.0, "75%": 0.0},
                "win_rate": 0.0,
            }

        df = self.fills_df.copy()

        # Trade size
        avg_size = float(df["qty"].abs().mean()) if "qty" in df.columns else 0.0

        # PnL analysis
        if "realized_pnl" in df.columns:
            pnl_col = "realized_pnl"
        elif "price" in df.columns and "qty" in df.columns:
            df["pnl"] = df["price"] * df["qty"]
            pnl_col = "pnl"
        else:
            pnl_col = None

        if pnl_col:
            avg_pnl = float(df[pnl_col].mean())
            pnl_percentiles = {
                "25%": float(df[pnl_col].quantile(0.25)),
                "50%": float(df[pnl_col].quantile(0.50)),
                "75%": float(df[pnl_col].quantile(0.75)),
            }
            win_rate = float((df[pnl_col] > 0).sum() / len(df) * 100)
        else:
            avg_pnl = 0.0
            pnl_percentiles = {"25%": 0.0, "50%": 0.0, "75%": 0.0}
            win_rate = 0.0

        return {
            "count": len(df),
            "avg_size": avg_size,
            "avg_pnl": avg_pnl,
            "pnl_percentiles": pnl_percentiles,
            "win_rate": win_rate,
        }

    def analyze_trade_timing(self) -> pd.DataFrame:
        """Group trades by hour/day and calculate avg PnL.

        Returns:
            DataFrame with hour_of_day, day_of_week, avg_pnl, count
        """
        if self.fills_df.empty:
            return pd.DataFrame(columns=["hour_of_day", "day_of_week", "avg_pnl", "count"])

        df = self.fills_df.copy()

        # Ensure timestamp
        if "ts_fill_ns" in df.columns and "timestamp" not in df.columns:
            df["timestamp"] = pd.to_datetime(df["ts_fill_ns"], unit="ns")
        elif "timestamp" in df.columns and not pd.api.types.is_datetime64_any_dtype(
            df["timestamp"]
        ):
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Extract time features
        df["hour_of_day"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek

        # PnL column
        if "realized_pnl" in df.columns:
            pnl_col = "realized_pnl"
        elif "price" in df.columns and "qty" in df.columns:
            df["pnl"] = df["price"] * df["qty"]
            pnl_col = "pnl"
        else:
            df["pnl"] = 0.0
            pnl_col = "pnl"

        # Group by hour and day
        grouped = (
            df.groupby(["hour_of_day", "day_of_week"])[pnl_col].agg(["mean", "count"]).reset_index()
        )
        grouped.columns = ["hour_of_day", "day_of_week", "avg_pnl", "count"]

        return grouped

    def calculate_exposure(self) -> pd.DataFrame:
        """Time series of capital deployed (0 = all cash, 1 = fully invested).

        Returns:
            DataFrame with timestamp index and exposure column
        """
        if self.positions_df.empty:
            return pd.DataFrame(columns=["exposure"])

        df = self.positions_df.copy()

        # Ensure timestamp
        if "ts_ns" in df.columns:
            df["timestamp"] = pd.to_datetime(df["ts_ns"], unit="ns")
        df = df.set_index("timestamp")

        # Calculate exposure as position_value / total_equity
        if "total_equity" in df.columns:
            if "total_position_value" in df.columns:
                position_value = df["total_position_value"]
            elif "cash" in df.columns:
                position_value = df["total_equity"] - df["cash"]
            else:
                position_value = df["total_equity"] * 0.5  # Assume 50% deployed

            exposure = position_value / df["total_equity"]
            exposure = exposure.clip(lower=0.0, upper=1.0)
        else:
            exposure = pd.Series(0.5, index=df.index)  # Default 50%

        result = pd.DataFrame({"exposure": exposure})
        return result

    def correlation_with_benchmark(
        self,
        benchmark_returns: pd.Series,
    ) -> dict[str, float]:
        """Calculate correlation, beta, alpha vs. benchmark.

        Args:
            benchmark_returns: Series of benchmark returns (same frequency as strategy)

        Returns:
            Dict with keys: correlation, beta, alpha
        """
        # Calculate strategy returns from positions
        if self.positions_df.empty:
            return {"correlation": 0.0, "beta": 0.0, "alpha": 0.0}

        df = self.positions_df.copy()

        if "ts_ns" in df.columns:
            df["timestamp"] = pd.to_datetime(df["ts_ns"], unit="ns")
        df = df.sort_values("timestamp")

        if "total_equity" not in df.columns:
            return {"correlation": 0.0, "beta": 0.0, "alpha": 0.0}

        # Calculate returns
        strategy_returns = df["total_equity"].pct_change().dropna()

        # Align with benchmark
        if len(strategy_returns) == 0 or len(benchmark_returns) == 0:
            return {"correlation": 0.0, "beta": 0.0, "alpha": 0.0}

        # Simple correlation (assuming same frequency)
        min_len = min(len(strategy_returns), len(benchmark_returns))
        strat_ret = strategy_returns.iloc[:min_len]
        bench_ret = benchmark_returns.iloc[:min_len]

        # Calculate correlation coefficient
        corr_result = strat_ret.corr(bench_ret)
        correlation = float(corr_result) if pd.notna(corr_result) else 0.0

        # Beta = Cov(strategy, benchmark) / Var(benchmark)
        cov_result = strat_ret.cov(bench_ret)
        covariance = float(cov_result) if pd.notna(cov_result) else 0.0

        var_result = bench_ret.var()
        # Handle scalar conversion properly
        if pd.notna(var_result):
            if hasattr(var_result, "item"):
                # numpy scalar - use item() to get Python native type
                item_val = var_result.item()
                benchmark_variance = float(item_val) if isinstance(item_val, (int, float)) else 0.0
            elif isinstance(var_result, (int, float)):
                benchmark_variance = float(var_result)
            else:
                # Fallback for other numeric types
                benchmark_variance = 0.0
        else:
            benchmark_variance = 0.0

        beta = covariance / benchmark_variance if benchmark_variance > 0 else 0.0

        # Alpha = Avg(strategy_return) - Beta * Avg(benchmark_return)
        strat_mean = strat_ret.mean()
        bench_mean = bench_ret.mean()
        alpha = (
            float(strat_mean - beta * bench_mean)
            if pd.notna(strat_mean) and pd.notna(bench_mean)
            else 0.0
        )

        return {
            "correlation": correlation,
            "beta": beta,
            "alpha": alpha,
        }
