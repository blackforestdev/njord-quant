"""Data validation tools for research analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

    from research.data_reader import DataReader
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]

    try:
        from research.data_reader import DataReader
    except ImportError:
        DataReader = None  # type: ignore[assignment,misc]


class DataValidator:
    """Validate data quality and detect anomalies."""

    def __init__(self, reader: DataReader) -> None:
        if pd is None:
            raise ImportError("pandas is required for DataValidator")
        self.reader = reader

    def check_gaps(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
    ) -> list[tuple[int, int]]:
        """Identify gaps in time series.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1m", "1h", "1d")
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            List of (gap_start_ts, gap_end_ts) tuples
        """
        df = self.reader.read_ohlcv(
            symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        )

        if df.empty or len(df) < 2:
            return []

        # Parse timeframe to get expected interval
        interval_ns = self._parse_timeframe_to_ns(timeframe)

        # Get timestamps
        if "ts_open" in df.columns:
            timestamps = sorted(df["ts_open"].tolist())
        else:
            return []

        # Find gaps
        gaps: list[tuple[int, int]] = []
        for i in range(len(timestamps) - 1):
            current_ts = timestamps[i]
            next_ts = timestamps[i + 1]
            expected_next = current_ts + interval_ns

            # If gap is larger than expected interval
            if next_ts > expected_next:
                gaps.append((current_ts + interval_ns, next_ts))

        return gaps

    def check_price_anomalies(
        self,
        df: pd.DataFrame,
        *,
        spike_threshold: float = 0.1,  # 10% move
        flatline_periods: int = 10,  # consecutive identical prices
    ) -> dict[str, list[int]]:
        """Detect price spikes and flatlines.

        Args:
            df: DataFrame with OHLCV data
            spike_threshold: Percentage threshold for spike detection (0.1 = 10%)
            flatline_periods: Number of consecutive identical prices to flag

        Returns:
            {"spikes": [ts1, ts2, ...], "flatlines": [ts1, ts2, ...]}
        """
        if df.empty:
            return {"spikes": [], "flatlines": []}

        spikes: list[int] = []
        flatlines: list[int] = []

        # Check for spikes using close prices
        if "close" in df.columns:
            close_prices = df["close"].values
            returns = []
            for i in range(1, len(close_prices)):
                if close_prices[i - 1] != 0:
                    ret = (close_prices[i] - close_prices[i - 1]) / close_prices[i - 1]
                    returns.append(ret)
                else:
                    returns.append(0.0)

            # Detect spikes
            timestamp_col = "ts_open" if "ts_open" in df.columns else "timestamp"
            if timestamp_col in df.columns:
                timestamps = df[timestamp_col].tolist()
                for i, ret in enumerate(returns):
                    if abs(ret) > spike_threshold:
                        spikes.append(int(timestamps[i + 1]))

        # Check for flatlines
        if "close" in df.columns:
            close_prices = df["close"].values
            timestamp_col = "ts_open" if "ts_open" in df.columns else "timestamp"

            if timestamp_col in df.columns:
                timestamps = df[timestamp_col].tolist()
                consecutive_count = 1
                for i in range(1, len(close_prices)):
                    if close_prices[i] == close_prices[i - 1]:
                        consecutive_count += 1
                        if consecutive_count >= flatline_periods:
                            flatlines.append(int(timestamps[i]))
                    else:
                        consecutive_count = 1

        return {"spikes": spikes, "flatlines": flatlines}

    def validate_ohlcv_consistency(
        self,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """Check OHLCV bar consistency.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            List of inconsistencies: [{"ts": ts, "issue": "high < low"}, ...]
        """
        if df.empty:
            return []

        issues: list[dict[str, Any]] = []

        timestamp_col = "ts_open" if "ts_open" in df.columns else "timestamp"
        if timestamp_col not in df.columns:
            return issues

        required_cols = ["open", "high", "low", "close"]
        if not all(col in df.columns for col in required_cols):
            return issues

        for idx in range(len(df)):
            row = df.iloc[idx]
            ts = int(row[timestamp_col])
            open_price = float(row["open"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])

            # Check: high >= low
            if high_price < low_price:
                issues.append(
                    {"ts": ts, "issue": "high < low", "high": high_price, "low": low_price}
                )

            # Check: high >= open
            if high_price < open_price:
                issues.append(
                    {"ts": ts, "issue": "high < open", "high": high_price, "open": open_price}
                )

            # Check: high >= close
            if high_price < close_price:
                issues.append(
                    {"ts": ts, "issue": "high < close", "high": high_price, "close": close_price}
                )

            # Check: low <= open
            if low_price > open_price:
                issues.append(
                    {"ts": ts, "issue": "low > open", "low": low_price, "open": open_price}
                )

            # Check: low <= close
            if low_price > close_price:
                issues.append(
                    {"ts": ts, "issue": "low > close", "low": low_price, "close": close_price}
                )

            # Check: prices are positive
            if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
                issues.append({"ts": ts, "issue": "non-positive price"})

        return issues

    def check_fill_anomalies(
        self,
        fills_df: pd.DataFrame,
        market_prices_df: pd.DataFrame,
        *,
        deviation_threshold: float = 0.02,  # 2% from market
    ) -> list[dict[str, Any]]:
        """Identify fills with suspicious prices.

        Args:
            fills_df: DataFrame with fill data
            market_prices_df: DataFrame with market OHLCV data
            deviation_threshold: Maximum allowed deviation from market price (0.02 = 2%)

        Returns:
            List of suspicious fills with deviation info
        """
        if fills_df.empty or market_prices_df.empty:
            return []

        anomalies: list[dict[str, Any]] = []

        # Create timestamp index for market prices
        timestamp_col = "ts_open" if "ts_open" in market_prices_df.columns else "timestamp"
        if timestamp_col not in market_prices_df.columns:
            return anomalies

        market_prices_df = market_prices_df.copy()
        market_prices_df["ts_index"] = market_prices_df[timestamp_col]

        # Check each fill
        fill_ts_col = "ts_fill_ns" if "ts_fill_ns" in fills_df.columns else "timestamp"
        if fill_ts_col not in fills_df.columns or "price" not in fills_df.columns:
            return anomalies

        for idx in range(len(fills_df)):
            fill_row = fills_df.iloc[idx]
            fill_ts = int(fill_row[fill_ts_col])
            fill_price = float(fill_row["price"])

            # Find closest market price
            market_prices_df["ts_diff"] = (market_prices_df["ts_index"] - fill_ts).abs()
            closest_idx = market_prices_df["ts_diff"].idxmin()
            closest_market = market_prices_df.loc[closest_idx]

            # Get market price range (use close as reference)
            market_price = float(closest_market["close"]) if "close" in closest_market else 0.0

            if market_price > 0:
                deviation = abs(fill_price - market_price) / market_price

                if deviation > deviation_threshold:
                    anomalies.append(
                        {
                            "ts": fill_ts,
                            "fill_price": fill_price,
                            "market_price": market_price,
                            "deviation_pct": deviation * 100,
                        }
                    )

        return anomalies

    def generate_quality_report(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
    ) -> dict[str, Any]:
        """Generate comprehensive data quality report.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1m", "1h", "1d")
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            Report dict with all validation results
        """
        df = self.reader.read_ohlcv(
            symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        )

        report: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "total_bars": len(df),
            "gaps": [],
            "price_anomalies": {"spikes": [], "flatlines": []},
            "consistency_issues": [],
            "summary": {},
        }

        if df.empty:
            return report

        # Check gaps
        gaps = self.check_gaps(symbol, timeframe, start_ts, end_ts)
        report["gaps"] = [(int(s), int(e)) for s, e in gaps]

        # Check price anomalies
        price_anomalies = self.check_price_anomalies(df)
        report["price_anomalies"] = price_anomalies

        # Validate consistency
        consistency_issues = self.validate_ohlcv_consistency(df)
        report["consistency_issues"] = consistency_issues

        # Generate summary (populate before calculating quality score)
        report["summary"] = {
            "total_gaps": len(gaps),
            "total_spikes": len(price_anomalies["spikes"]),
            "total_flatlines": len(price_anomalies["flatlines"]),
            "total_consistency_issues": len(consistency_issues),
        }

        # Calculate quality score after summary is populated
        report["summary"]["quality_score"] = self._calculate_quality_score(report)

        return report

    def _parse_timeframe_to_ns(self, timeframe: str) -> int:
        """Convert timeframe string to nanoseconds.

        Args:
            timeframe: Timeframe string (e.g., "1m", "5m", "1h", "1d")

        Returns:
            Interval in nanoseconds
        """
        import re

        match = re.match(r"(\d+)([smhd])", timeframe.lower())
        if not match:
            raise ValueError(f"Invalid timeframe format: {timeframe}")

        value = int(match.group(1))
        unit = match.group(2)

        multipliers = {
            "s": 1_000_000_000,  # seconds to nanoseconds
            "m": 60_000_000_000,  # minutes to nanoseconds
            "h": 3_600_000_000_000,  # hours to nanoseconds
            "d": 86_400_000_000_000,  # days to nanoseconds
        }

        return value * multipliers[unit]

    def _calculate_quality_score(self, report: dict[str, Any]) -> float:
        """Calculate overall quality score (0-100).

        Args:
            report: Quality report dict

        Returns:
            Quality score between 0 and 100
        """
        total_bars = report["total_bars"]
        if total_bars == 0:
            return 0.0

        # Deduct points for issues
        score = 100.0
        score -= min(20.0, float(report["summary"]["total_gaps"]) * 2)  # Max 20 points for gaps
        score -= min(
            20.0, float(report["summary"]["total_spikes"]) * 0.5
        )  # Max 20 points for spikes
        score -= min(
            10.0, float(report["summary"]["total_flatlines"]) * 0.2
        )  # Max 10 points for flatlines
        score -= min(
            50.0, float(report["summary"]["total_consistency_issues"]) * 5
        )  # Max 50 for consistency

        return float(max(0.0, score))
