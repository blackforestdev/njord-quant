"""Data aggregation utilities for research analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]

from research.data_reader import DataReader


class DataAggregator:
    """Aggregate and transform market data for research purposes."""

    def __init__(self, reader: DataReader) -> None:
        if pd is None:
            raise ImportError("pandas is required for DataAggregator")
        self.reader = reader

    def resample_ohlcv(
        self,
        df: pd.DataFrame,
        target_timeframe: str,
        *,
        align_to_wall_clock: bool = True,
    ) -> pd.DataFrame:
        """Resample OHLCV bars to a different timeframe.

        Args:
            df: DataFrame with OHLCV columns and datetime index
            target_timeframe: Target timeframe (e.g., "5T", "1H", "1D")
            align_to_wall_clock: Align bars to wall-clock boundaries

        Returns:
            Resampled DataFrame with OHLCV columns
        """
        if df.empty:
            return df.copy()

        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            else:
                raise ValueError("DataFrame must have datetime index or 'timestamp' column")

        # Resample with proper OHLCV aggregation
        origin = "start_day" if align_to_wall_clock else "start"
        resampler = df.resample(target_timeframe, origin=origin)

        result = pd.DataFrame(
            {
                "open": resampler["open"].first(),
                "high": resampler["high"].max(),
                "low": resampler["low"].min(),
                "close": resampler["close"].last(),
                "volume": resampler["volume"].sum(),
            }
        )

        # Drop rows where all OHLC values are NaN (no data in that period)
        result = result.dropna(subset=["open", "high", "low", "close"], how="all")

        return result

    def add_indicators(
        self,
        df: pd.DataFrame,
        indicators: list[str],
    ) -> pd.DataFrame:
        """Add technical indicators to DataFrame.

        Supported indicators:
        - sma_N: Simple moving average (N periods)
        - ema_N: Exponential moving average (N periods)
        - rsi_N: Relative strength index (N periods)
        - macd: MACD (12, 26, 9)
        - bbands_N_K: Bollinger Bands (N periods, K std devs)

        Args:
            df: DataFrame with at least 'close' column
            indicators: List of indicator specifications

        Returns:
            DataFrame with indicator columns added
        """
        if df.empty:
            return df.copy()

        result = df.copy()

        for indicator in indicators:
            if indicator.startswith("sma_"):
                period = int(indicator.split("_")[1])
                result[indicator] = self._calculate_sma(result["close"], period)
            elif indicator.startswith("ema_"):
                period = int(indicator.split("_")[1])
                result[indicator] = self._calculate_ema(result["close"], period)
            elif indicator.startswith("rsi_"):
                period = int(indicator.split("_")[1])
                result[indicator] = self._calculate_rsi(result["close"], period)
            elif indicator == "macd":
                macd_line, signal_line, histogram = self._calculate_macd(result["close"])
                result["macd"] = macd_line
                result["macd_signal"] = signal_line
                result["macd_histogram"] = histogram
            elif indicator.startswith("bbands_"):
                parts = indicator.split("_")
                period = int(parts[1])
                std_dev = float(parts[2])
                upper, middle, lower = self._calculate_bbands(result["close"], period, std_dev)
                result[f"bbands_upper_{period}_{std_dev}"] = upper
                result[f"bbands_middle_{period}_{std_dev}"] = middle
                result[f"bbands_lower_{period}_{std_dev}"] = lower
            else:
                raise ValueError(f"Unsupported indicator: {indicator}")

        return result

    def merge_symbols(
        self,
        symbol_dfs: dict[str, pd.DataFrame],
        *,
        how: Literal["inner", "outer"] = "outer",
        fill_method: Literal["ffill", "none"] = "ffill",
    ) -> pd.DataFrame:
        """Merge multiple symbol DataFrames with aligned timestamps.

        Args:
            symbol_dfs: Dict mapping symbol to DataFrame
            how: Join method ("inner" or "outer")
            fill_method: Fill method for missing values ("ffill" or "none")

        Returns:
            Merged DataFrame with multi-level columns (symbol, field)
        """
        if not symbol_dfs:
            return pd.DataFrame()

        # Ensure all DataFrames have datetime index
        aligned_dfs = {}
        for symbol, df in symbol_dfs.items():
            if not isinstance(df.index, pd.DatetimeIndex):
                if "timestamp" in df.columns:
                    df = df.set_index("timestamp")
                else:
                    raise ValueError(f"DataFrame for {symbol} must have datetime index")
            aligned_dfs[symbol] = df

        # Concatenate with multi-level columns
        result = pd.concat(aligned_dfs, axis=1, join=how, keys=aligned_dfs.keys())

        # Apply fill method
        if fill_method == "ffill":
            result = result.ffill()

        return result

    # Technical indicator implementations

    def _calculate_sma(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average."""
        return series.rolling(window=period, min_periods=period).mean()

    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False, min_periods=period).mean()

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = series.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    def _calculate_macd(
        self,
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD (Moving Average Convergence Divergence).

        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
        ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def _calculate_bbands(
        self,
        series: pd.Series,
        period: int,
        std_dev: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands.

        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        middle = series.rolling(window=period, min_periods=period).mean()
        std = series.rolling(window=period, min_periods=period).std()

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        return upper, middle, lower
