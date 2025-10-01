"""Jupyter notebook helper utilities for research analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


class NotebookHelper:
    """Convenience functions for interactive Jupyter sessions."""

    def __init__(self) -> None:
        if pd is None:
            raise ImportError("pandas is required for NotebookHelper")

    def quick_plot_equity(
        self,
        result: BacktestResult,
        *,
        title: str | None = None,
        figsize: tuple[int, int] = (12, 6),
    ) -> Any:
        """Plot equity curve with matplotlib.

        Args:
            result: BacktestResult to plot
            title: Optional plot title
            figsize: Figure size (width, height)

        Returns:
            matplotlib Figure object
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as e:
            raise ImportError("matplotlib is required for plotting") from e

        if not result.equity_curve:
            raise ValueError("BacktestResult has no equity curve data")

        # Convert to DataFrame
        timestamps = [ts for ts, _ in result.equity_curve]
        equity_values = [eq for _, eq in result.equity_curve]

        df = pd.DataFrame(
            {"timestamp": pd.to_datetime(timestamps, unit="ns"), "equity": equity_values}
        )

        # Create plot
        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(df["timestamp"], df["equity"], linewidth=2, label="Equity")
        ax.axhline(
            y=result.initial_capital,
            color="gray",
            linestyle="--",
            alpha=0.5,
            label="Initial Capital",
        )

        # Labels and title
        ax.set_xlabel("Date")
        ax.set_ylabel("Equity ($)")
        plot_title = title if title else f"Equity Curve: {result.strategy_id}"
        ax.set_title(plot_title)
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Format y-axis as currency
        from matplotlib.ticker import FuncFormatter

        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:,.0f}"))

        return fig

    def quick_summary_table(
        self,
        results: dict[str, BacktestResult],
    ) -> pd.DataFrame:
        """Generate summary table of key metrics.

        Args:
            results: Dict mapping strategy_id to BacktestResult

        Returns:
            DataFrame with strategies as rows, metrics as columns
        """
        if not results:
            return pd.DataFrame()

        summary_data = []

        for strategy_id, result in results.items():
            row = {
                "Strategy": strategy_id,
                "Total Return %": result.total_return_pct,
                "Sharpe Ratio": result.sharpe_ratio,
                "Max Drawdown %": result.max_drawdown_pct,
                "Win Rate": result.win_rate if hasattr(result, "win_rate") else 0.0,
                "Profit Factor": result.profit_factor if hasattr(result, "profit_factor") else 0.0,
                "Num Trades": result.num_trades,
                "Initial Capital": result.initial_capital,
                "Final Capital": result.final_capital,
            }
            summary_data.append(row)

        df = pd.DataFrame(summary_data)

        # Set Strategy as index
        if "Strategy" in df.columns:
            df = df.set_index("Strategy")

        return df

    def compare_equity_curves(
        self,
        results: dict[str, BacktestResult],
        *,
        normalize: bool = True,
        title: str | None = None,
        figsize: tuple[int, int] = (12, 6),
    ) -> Any:
        """Plot multiple equity curves on same chart.

        Args:
            results: Dict mapping strategy_id to BacktestResult
            normalize: If True, normalize all curves to start at 100%
            title: Optional plot title
            figsize: Figure size (width, height)

        Returns:
            matplotlib Figure object
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as e:
            raise ImportError("matplotlib is required for plotting") from e

        if not results:
            raise ValueError("No results to plot")

        fig, ax = plt.subplots(figsize=figsize)

        for strategy_id, result in results.items():
            if not result.equity_curve:
                continue

            # Convert to DataFrame
            timestamps = [ts for ts, _ in result.equity_curve]
            equity_values = [eq for _, eq in result.equity_curve]

            # Normalize if requested
            if normalize:
                initial = result.initial_capital if result.initial_capital > 0 else equity_values[0]
                equity_values = [(eq / initial) * 100 for eq in equity_values]

            df = pd.DataFrame(
                {"timestamp": pd.to_datetime(timestamps, unit="ns"), "equity": equity_values}
            )

            # Plot
            ax.plot(df["timestamp"], df["equity"], linewidth=2, label=strategy_id)

        # Labels and title
        ax.set_xlabel("Date")
        ylabel = "Equity (%)" if normalize else "Equity ($)"
        ax.set_ylabel(ylabel)

        plot_title = title if title else "Strategy Comparison"
        ax.set_title(plot_title)
        ax.legend()
        ax.grid(True, alpha=0.3)

        if normalize:
            ax.axhline(y=100, color="gray", linestyle="--", alpha=0.5)
        else:
            from matplotlib.ticker import FuncFormatter

            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:,.0f}"))

        return fig

    def display_metrics_heatmap(
        self,
        results: dict[str, BacktestResult],
        *,
        metrics: list[str] | None = None,
        figsize: tuple[int, int] = (10, 8),
    ) -> Any:
        """Display heatmap of normalized metrics across strategies.

        Args:
            results: Dict mapping strategy_id to BacktestResult
            metrics: List of metric names to include (default: all)
            figsize: Figure size (width, height)

        Returns:
            matplotlib Figure object
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as e:
            raise ImportError("matplotlib is required for plotting") from e

        if not results:
            raise ValueError("No results to plot")

        # Build metrics DataFrame
        metrics_data = []
        for _strategy_id, result in results.items():
            row = {
                "total_return_pct": result.total_return_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": -result.max_drawdown_pct,  # Negative so higher is better
                "win_rate": result.win_rate if hasattr(result, "win_rate") else 0.0,
                "profit_factor": result.profit_factor if hasattr(result, "profit_factor") else 0.0,
            }
            metrics_data.append(row)

        df = pd.DataFrame(metrics_data, index=list(results.keys()))

        # Filter metrics if specified
        if metrics:
            available_metrics = [m for m in metrics if m in df.columns]
            df = df[available_metrics]

        # Normalize to 0-100 scale per metric
        normalized = pd.DataFrame()
        for col in df.columns:
            min_val = df[col].min()
            max_val = df[col].max()
            if max_val > min_val:
                normalized[col] = ((df[col] - min_val) / (max_val - min_val)) * 100
            else:
                normalized[col] = 50.0  # All same value

        # Create heatmap
        fig, ax = plt.subplots(figsize=figsize)

        # Convert to numpy array for imshow
        import numpy as np

        data = normalized.values
        im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=0, vmax=100)

        # Set ticks and labels
        ax.set_xticks(np.arange(len(normalized.columns)))
        ax.set_yticks(np.arange(len(normalized.index)))
        ax.set_xticklabels(normalized.columns)
        ax.set_yticklabels(normalized.index)

        # Rotate x-axis labels
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

        # Add colorbar
        cbar = ax.figure.colorbar(im, ax=ax)
        cbar.ax.set_ylabel("Normalized Score", rotation=-90, va="bottom")

        # Add text annotations
        for i in range(len(normalized.index)):
            for j in range(len(normalized.columns)):
                val = data[i, j]
                ax.text(j, i, f"{val:.0f}", ha="center", va="center", color="black")

        ax.set_title("Strategy Metrics Heatmap (Normalized 0-100)")
        fig.tight_layout()

        return fig

    def export_to_csv(
        self,
        result: BacktestResult,
        output_path: str,
    ) -> None:
        """Export equity curve to CSV file.

        Args:
            result: BacktestResult to export
            output_path: Path to output CSV file
        """
        if not result.equity_curve:
            raise ValueError("BacktestResult has no equity curve data")

        # Convert to DataFrame
        timestamps = [ts for ts, _ in result.equity_curve]
        equity_values = [eq for _, eq in result.equity_curve]

        df = pd.DataFrame(
            {"timestamp": pd.to_datetime(timestamps, unit="ns"), "equity": equity_values}
        )

        # Export
        df.to_csv(output_path, index=False)

    def style_dataframe(
        self,
        df: pd.DataFrame,
        *,
        gradient_cols: list[str] | None = None,
        precision: int = 2,
    ) -> Any:
        """Apply styling to DataFrame for notebook display.

        Args:
            df: DataFrame to style
            gradient_cols: Columns to apply gradient coloring
            precision: Decimal precision for numeric columns

        Returns:
            Styled DataFrame (or plain DataFrame if jinja2 not available)
        """
        try:
            styled = df.style.format(precision=precision, na_rep="-")

            # Apply gradient if specified
            if gradient_cols:
                available_cols = [col for col in gradient_cols if col in df.columns]
                if available_cols:
                    styled = styled.background_gradient(subset=available_cols, cmap="RdYlGn")

            return styled
        except AttributeError:
            # jinja2 not available, return plain DataFrame
            return df
