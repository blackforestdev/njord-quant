"""Strategy comparison tools for research analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from backtest.contracts import BacktestResult
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]

    try:
        from backtest.contracts import BacktestResult
    except ImportError:
        BacktestResult = None  # type: ignore[assignment,misc]


class StrategyComparison:
    """Compare multiple strategies side-by-side."""

    def __init__(self, strategy_results: dict[str, BacktestResult]) -> None:
        if pd is None:
            raise ImportError("pandas is required for StrategyComparison")
        self.strategy_results = strategy_results

    def normalize_equity_curves(
        self,
        target_capital: float = 100000.0,
    ) -> pd.DataFrame:
        """Normalize all equity curves to same starting capital.

        Args:
            target_capital: Starting capital to normalize all curves to

        Returns:
            DataFrame with datetime index and strategy columns
        """
        if not self.strategy_results:
            return pd.DataFrame()

        normalized_curves = {}

        for strategy_id, result in self.strategy_results.items():
            if not result.equity_curve:
                continue

            # Convert equity curve to DataFrame
            timestamps = [ts for ts, _ in result.equity_curve]
            equity_values = [eq for _, eq in result.equity_curve]

            # Normalize to target_capital
            initial_capital = result.initial_capital
            if initial_capital > 0:
                scaling_factor = target_capital / initial_capital
                normalized_values = [eq * scaling_factor for eq in equity_values]
            else:
                normalized_values = equity_values

            # Convert timestamps to datetime
            dt_index = pd.to_datetime(timestamps, unit="ns")
            normalized_curves[strategy_id] = pd.Series(
                normalized_values, index=dt_index, name=strategy_id
            )

        if not normalized_curves:
            return pd.DataFrame()

        # Combine into single DataFrame
        result_df = pd.DataFrame(normalized_curves)

        return result_df

    def compare_metrics(self) -> pd.DataFrame:
        """Return DataFrame comparing all metrics across strategies.

        Returns:
            DataFrame with strategies as rows and metrics as columns
        """
        if not self.strategy_results:
            return pd.DataFrame()

        metrics_data = []

        for strategy_id, result in self.strategy_results.items():
            metrics_dict = {
                "strategy_id": strategy_id,
                "total_return_pct": result.total_return_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
                "win_rate": result.win_rate if hasattr(result, "win_rate") else 0.0,
                "num_trades": result.num_trades,
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
            }

            metrics_data.append(metrics_dict)

        result_df = pd.DataFrame(metrics_data)

        # Set strategy_id as index
        if "strategy_id" in result_df.columns:
            result_df = result_df.set_index("strategy_id")

        return result_df

    def identify_divergence_periods(
        self,
        threshold: float = 0.1,
    ) -> list[tuple[int, int, str, str]]:
        """Identify time periods where strategies diverged significantly.

        Args:
            threshold: Minimum return difference to consider divergence (e.g., 0.1 = 10%)

        Returns:
            List of (start_ts, end_ts, outperformer, underperformer) tuples
        """
        if len(self.strategy_results) < 2:
            return []

        # Get normalized equity curves
        equity_df = self.normalize_equity_curves()

        if equity_df.empty or len(equity_df.columns) < 2:
            return []

        # Calculate returns for each strategy
        returns_df = equity_df.pct_change().fillna(0.0)

        # Calculate cumulative returns from start
        cumulative_returns = (1 + returns_df).cumprod() - 1

        divergence_periods = []
        in_divergence = False
        divergence_start_idx = None
        current_outperformer = None
        current_underperformer = None

        for i in range(len(cumulative_returns)):
            row = cumulative_returns.iloc[i]

            # Find max and min performers at this timestamp
            max_strategy = str(row.idxmax())
            min_strategy = str(row.idxmin())

            max_return = float(row.max())
            min_return = float(row.min())

            difference = max_return - min_return

            if difference >= threshold:
                # Divergence detected
                if not in_divergence:
                    # Start new divergence period
                    in_divergence = True
                    divergence_start_idx = i
                    current_outperformer = max_strategy
                    current_underperformer = min_strategy
                else:
                    # Update current leaders
                    current_outperformer = max_strategy
                    current_underperformer = min_strategy
            else:
                # No significant divergence
                if in_divergence:
                    # End of divergence period
                    if divergence_start_idx is not None:
                        start_ts = int(cumulative_returns.index[divergence_start_idx].value)
                        end_ts = int(cumulative_returns.index[i - 1].value)
                        divergence_periods.append(
                            (
                                start_ts,
                                end_ts,
                                current_outperformer or "",
                                current_underperformer or "",
                            )
                        )
                    in_divergence = False
                    divergence_start_idx = None

        # Handle open divergence at end
        if in_divergence and divergence_start_idx is not None:
            start_ts = int(cumulative_returns.index[divergence_start_idx].value)
            end_ts = int(cumulative_returns.index[-1].value)
            divergence_periods.append(
                (start_ts, end_ts, current_outperformer or "", current_underperformer or "")
            )

        return divergence_periods

    def statistical_significance(
        self,
        strategy_a: str,
        strategy_b: str,
        *,
        method: str = "ttest",
    ) -> dict[str, float]:
        """Test if performance difference is statistically significant.

        Args:
            strategy_a: First strategy ID
            strategy_b: Second strategy ID
            method: Statistical test method ("ttest" or "bootstrap")

        Returns:
            Dict with keys: p_value, confidence, mean_diff
        """
        if strategy_a not in self.strategy_results or strategy_b not in self.strategy_results:
            return {"p_value": 1.0, "confidence": 0.0, "mean_diff": 0.0}

        result_a = self.strategy_results[strategy_a]
        result_b = self.strategy_results[strategy_b]

        # Get equity curves and calculate returns
        if not result_a.equity_curve or not result_b.equity_curve:
            return {"p_value": 1.0, "confidence": 0.0, "mean_diff": 0.0}

        # Convert to pandas Series
        equity_a = pd.Series([eq for _, eq in result_a.equity_curve])
        equity_b = pd.Series([eq for _, eq in result_b.equity_curve])

        # Calculate returns
        returns_a = equity_a.pct_change().dropna()
        returns_b = equity_b.pct_change().dropna()

        if len(returns_a) == 0 or len(returns_b) == 0:
            return {"p_value": 1.0, "confidence": 0.0, "mean_diff": 0.0}

        mean_diff = float(returns_a.mean() - returns_b.mean())

        if method == "ttest":
            # Perform t-test
            p_value = self._ttest(returns_a, returns_b)
        elif method == "bootstrap":
            # Perform bootstrap test
            p_value = self._bootstrap_test(returns_a, returns_b)
        else:
            raise ValueError(f"Unsupported method: {method}")

        confidence = (1.0 - p_value) * 100.0

        return {
            "p_value": p_value,
            "confidence": confidence,
            "mean_diff": mean_diff,
        }

    def _ttest(self, returns_a: pd.Series, returns_b: pd.Series) -> float:
        """Perform Welch's t-test for unequal variances.

        Returns:
            p-value (two-tailed)
        """
        import numpy as np

        n_a = len(returns_a)
        n_b = len(returns_b)

        if n_a < 2 or n_b < 2:
            return 1.0

        # Use proper scalar conversion for pandas Series means/vars
        mean_a_val = returns_a.mean()
        mean_a = float(mean_a_val) if isinstance(mean_a_val, (int, float)) else 0.0

        mean_b_val = returns_b.mean()
        mean_b = float(mean_b_val) if isinstance(mean_b_val, (int, float)) else 0.0

        var_a_val = returns_a.var()
        var_a = float(var_a_val) if isinstance(var_a_val, (int, float)) else 0.0

        var_b_val = returns_b.var()
        var_b = float(var_b_val) if isinstance(var_b_val, (int, float)) else 0.0

        # Handle zero variance
        if var_a == 0 and var_b == 0:
            return 1.0 if mean_a == mean_b else 0.0

        # Welch's t-statistic
        se = np.sqrt(var_a / n_a + var_b / n_b)

        if se == 0:
            return 1.0

        t_stat = (mean_a - mean_b) / se

        # Degrees of freedom (Welch-Satterthwaite equation)
        if var_a == 0 or var_b == 0:
            df = float(max(n_a, n_b) - 1)
        else:
            numerator = (var_a / n_a + var_b / n_b) ** 2
            denominator = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
            df = float(numerator / denominator if denominator > 0 else max(n_a, n_b) - 1)

        # Two-tailed p-value using t-distribution
        # Simplified approximation
        p_value = self._t_distribution_pvalue(abs(t_stat), df)

        return p_value

    def _bootstrap_test(
        self, returns_a: pd.Series, returns_b: pd.Series, n_iterations: int = 1000
    ) -> float:
        """Perform bootstrap hypothesis test.

        Returns:
            p-value
        """

        observed_diff = float(returns_a.mean() - returns_b.mean())

        # Pool the returns
        pooled = pd.concat([returns_a, returns_b])
        n_a = len(returns_a)

        # Bootstrap resampling
        count_extreme = 0

        for _ in range(n_iterations):
            # Resample with replacement
            resampled = pooled.sample(n=len(pooled), replace=True)
            boot_a = resampled.iloc[:n_a]
            boot_b = resampled.iloc[n_a:]

            boot_diff = float(boot_a.mean() - boot_b.mean())

            # Count how often we see a difference as extreme as observed
            if abs(boot_diff) >= abs(observed_diff):
                count_extreme += 1

        p_value = count_extreme / n_iterations

        return p_value

    def _t_distribution_pvalue(self, t_stat: float, df: float) -> float:
        """Approximate p-value for t-distribution (two-tailed).

        Uses a simple approximation for the t-distribution CDF.
        """
        import math

        if df <= 0:
            return 1.0

        # For large df, t-distribution approximates normal distribution
        if df > 30:
            # Use standard normal approximation
            # P(|Z| > |t_stat|) ≈ 2 * (1 - Φ(|t_stat|))
            z = abs(t_stat)
            # Approximation of standard normal CDF
            p_one_tail = 0.5 * (1.0 + math.erf(-z / math.sqrt(2)))
            return 2.0 * p_one_tail

        # For small df, use approximation based on df
        # Very rough approximation - in production, use scipy.stats.t
        x = df / (df + t_stat**2)
        p_value = float(x ** (df / 2))

        return min(1.0, max(0.0, p_value))
