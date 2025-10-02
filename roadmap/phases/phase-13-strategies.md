## Phase 13 — Advanced Strategy Toolkit 📋

**Purpose:** Implement advanced quantitative strategies with factor models, ML feature engineering, and ensemble meta-strategies.

**Current Status:** Phase 12 complete — Compliance & Audit fully operational
**Next Phase:** Phase 14 — Simulation Harness

**Critical Design Principles:**
1. **Offline Training Only:** No live model training/inference — all ML models pre-trained and versioned
2. **Deterministic Execution:** All feature calculations must be deterministic and reproducible
3. **No New Runtime Dependencies:** Use existing stack (numpy/pandas from Phase 7 optional group)
4. **Strategy Plugin Architecture:** Build on existing strategy framework (base.py, registry.py)
5. **Risk Engine Integration:** All strategies emit OrderIntent → Risk Engine (no bypass)

---

### Phase 13.0 — Factor Model Contracts 📋
**Status:** Planned
**Dependencies:** 12.9 (Compliance Documentation)
**Task:** Define factor calculation and scoring contracts

**Contracts:**
```python
from typing import Literal, Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class FactorValue:
    """Single factor measurement."""
    factor_name: str
    symbol: str
    timestamp_ns: int
    value: float
    zscore: float | None  # Standardized value (-3 to +3 typically)
    percentile: float | None  # Rank percentile (0.0 to 1.0)
    metadata: dict[str, Any]  # Calculation params, lookback, etc.

@dataclass(frozen=True)
class FactorScore:
    """Multi-factor composite score."""
    symbol: str
    timestamp_ns: int
    factors: dict[str, float]  # {factor_name: value}
    composite_score: float  # Weighted combination
    signal_strength: float  # Confidence (0.0 to 1.0)
    regime: Literal["trending", "mean_reverting", "neutral", "volatile"]

@dataclass(frozen=True)
class FactorConfig:
    """Factor calculation configuration."""
    factor_name: str
    lookback_periods: int
    calculation_type: Literal["momentum", "mean_reversion", "carry", "volatility", "volume"]
    params: dict[str, Any]  # Factor-specific parameters
    weight: float  # Weight in composite score (0.0 to 1.0)
    enabled: bool

class FactorCalculator(Protocol):
    """Protocol for factor calculators."""

    def calculate(
        self,
        df: pd.DataFrame,  # OHLCV data
        lookback: int
    ) -> pd.Series:
        """Calculate factor values.

        Args:
            df: OHLCV DataFrame with columns [open, high, low, close, volume]
            lookback: Number of periods for calculation

        Returns:
            Series of factor values (same index as df)
        """
        ...

    def standardize(
        self,
        values: pd.Series,
        method: Literal["zscore", "percentile", "minmax"] = "zscore"
    ) -> pd.Series:
        """Standardize factor values."""
        ...
```

**Files:**
- `strategies/factors/contracts.py` (150 LOC)
- `tests/test_factor_contracts.py`

**Acceptance:**
- All contracts immutable and typed
- All timestamps use `*_ns` suffix
- Serializable to/from dict
- FactorCalculator protocol defined (not ABC - allows flexible implementations)
- Validation: lookback > 0, weight in [0, 1], signal_strength in [0, 1]
- Test verifies protocol compliance with mock calculator
- `make fmt lint type test` green

---

### Phase 13.1 — Momentum Factor Calculator 📋
**Status:** Planned
**Dependencies:** 13.0 (Factor Model Contracts)
**Task:** Implement momentum-based factor calculations

**Behavior:**
- Calculate multiple momentum signals: price momentum, volume momentum, trend strength
- Support configurable lookback periods (1d, 7d, 30d, 90d)
- Standardize outputs (z-score normalization)
- Deterministic calculation (no randomness)
- Efficient vectorized pandas operations

**API:**
```python
class MomentumCalculator:
    """Momentum factor calculator."""

    def __init__(
        self,
        short_period: int = 10,
        medium_period: int = 30,
        long_period: int = 90
    ): ...

    def calculate_price_momentum(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> pd.Series:
        """Calculate price momentum as log return.

        Formula: log(close / close[t-lookback])

        Returns:
            Series of momentum values
        """
        pass

    def calculate_volume_momentum(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> pd.Series:
        """Calculate volume momentum ratio.

        Formula: volume_ma[short] / volume_ma[long] - 1

        Returns:
            Series of volume momentum values
        """
        pass

    def calculate_trend_strength(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> pd.Series:
        """Calculate trend strength using linear regression R².

        Fit linear regression to close prices over lookback period.
        R² close to 1 indicates strong trend.

        Returns:
            Series of R² values (0 to 1)
        """
        pass

    def calculate_composite_momentum(
        self,
        df: pd.DataFrame,
        weights: dict[str, float] | None = None
    ) -> FactorScore:
        """Calculate weighted composite momentum score.

        Args:
            df: OHLCV DataFrame
            weights: Optional custom weights for each factor
                    Default: {"price": 0.5, "volume": 0.3, "trend": 0.2}

        Returns:
            FactorScore with composite momentum
        """
        pass
```

**Supported Factors:**
- **Price Momentum:** Log returns over various lookbacks (1d, 7d, 30d, 90d)
- **Volume Momentum:** Volume MA ratio (short/long - 1)
- **Trend Strength:** Linear regression R² over lookback
- **Acceleration:** Second derivative of price (momentum of momentum)

**Files:**
- `strategies/factors/momentum.py` (200 LOC)
- `tests/test_momentum_calculator.py`

**Acceptance:**
- All calculations deterministic (same input → same output)
- Price momentum uses log returns (handles large price changes)
- Volume momentum normalized against long-term average
- Trend strength R² in [0, 1] range
- Composite score weights sum to 1.0
- Test includes golden dataset (fixed OHLCV → known momentum values)
- Performance: <10ms for 1000 bars
- `make fmt lint type test` green

---

### Phase 13.2 — Mean Reversion Factor Calculator 📋
**Status:** Planned
**Dependencies:** 13.1 (Momentum Factor Calculator)
**Task:** Implement mean reversion factor calculations

**Behavior:**
- Calculate z-score distance from moving average
- Bollinger Band position (where price sits in band)
- RSI divergence from neutral (50)
- Half-life of mean reversion estimation
- Identify oversold/overbought extremes

**API:**
```python
class MeanReversionCalculator:
    """Mean reversion factor calculator."""

    def __init__(
        self,
        ma_period: int = 20,
        std_period: int = 20,
        rsi_period: int = 14
    ): ...

    def calculate_zscore_from_ma(
        self,
        df: pd.DataFrame,
        ma_period: int
    ) -> pd.Series:
        """Calculate z-score distance from moving average.

        Formula: (close - SMA) / rolling_std

        Returns:
            Series of z-scores (negative = below MA, positive = above MA)
        """
        pass

    def calculate_bb_position(
        self,
        df: pd.DataFrame,
        ma_period: int,
        std_multiplier: float = 2.0
    ) -> pd.Series:
        """Calculate price position within Bollinger Bands.

        Formula: (close - lower_band) / (upper_band - lower_band)

        Returns:
            Series in [0, 1] range (0.5 = at middle band)
        """
        pass

    def calculate_rsi_divergence(
        self,
        df: pd.DataFrame,
        rsi_period: int = 14
    ) -> pd.Series:
        """Calculate RSI divergence from neutral (50).

        Formula: (RSI - 50) / 50  # Normalized to [-1, 1]

        Returns:
            Series of RSI divergence (-1 = oversold, +1 = overbought)
        """
        pass

    def estimate_half_life(
        self,
        df: pd.DataFrame,
        lookback: int = 100
    ) -> float:
        """Estimate mean reversion half-life using Ornstein-Uhlenbeck.

        Fit AR(1) model: Δprice[t] = λ(μ - price[t-1]) + ε
        Half-life = -log(2) / log(1 + λ)

        Returns:
            Half-life in periods (lower = faster mean reversion)
        """
        pass

    def calculate_composite_mean_reversion(
        self,
        df: pd.DataFrame,
        weights: dict[str, float] | None = None
    ) -> FactorScore:
        """Calculate weighted composite mean reversion score.

        Args:
            weights: Optional custom weights
                    Default: {"zscore": 0.4, "bb_position": 0.3, "rsi": 0.3}

        Returns:
            FactorScore with composite mean reversion signal
        """
        pass
```

**Supported Factors:**
- **Z-Score from MA:** Distance from SMA in standard deviations
- **Bollinger Band Position:** Where price sits in BB channel (0-1)
- **RSI Divergence:** Distance from neutral RSI (50)
- **Half-Life:** Speed of mean reversion (Ornstein-Uhlenbeck estimate)

**Files:**
- `strategies/factors/mean_reversion.py` (220 LOC)
- `tests/test_mean_reversion_calculator.py`

**Acceptance:**
- Z-score calculation matches pandas rolling z-score
- BB position in [0, 1] range (clamped if price outside bands)
- RSI divergence normalized to [-1, 1]
- Half-life estimation uses AR(1) regression
- Composite score weighted average of standardized factors
- Test includes extreme scenarios (price at band edges, RSI at 0/100)
- Performance: <15ms for 1000 bars
- `make fmt lint type test` green

---

### Phase 13.3 — Carry & Volatility Factors 📋
**Status:** Planned
**Dependencies:** 13.2 (Mean Reversion Factor Calculator)
**Task:** Implement carry and volatility-based factors

**Behavior:**
- Funding rate carry (for perpetual futures)
- Volatility regime detection (low/medium/high)
- Volatility risk premium (realized vs implied)
- Parkinson volatility estimator (high-low range)
- Skewness and kurtosis for distribution analysis

**API:**
```python
class CarryVolatilityCalculator:
    """Carry and volatility factor calculator."""

    def __init__(
        self,
        vol_lookback: int = 20,
        regime_threshold: dict[str, float] | None = None
    ): ...

    def calculate_realized_volatility(
        self,
        df: pd.DataFrame,
        lookback: int,
        annualize: bool = True
    ) -> pd.Series:
        """Calculate realized volatility from returns.

        Formula: std(log_returns) * sqrt(periods_per_year)

        Args:
            annualize: If True, scale to annual volatility

        Returns:
            Series of realized volatility
        """
        pass

    def calculate_parkinson_volatility(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> pd.Series:
        """Calculate Parkinson (high-low) volatility estimator.

        More efficient than close-to-close volatility.
        Formula: sqrt( (1/(4*log(2))) * mean((log(high/low))²) )

        Returns:
            Series of Parkinson volatility
        """
        pass

    def detect_volatility_regime(
        self,
        df: pd.DataFrame,
        lookback: int,
        thresholds: dict[str, float] | None = None
    ) -> pd.Series:
        """Classify volatility regime.

        Args:
            thresholds: Dict with "low", "medium", "high" percentile cutoffs
                       Default: {"low": 0.33, "high": 0.67}

        Returns:
            Series of regime labels: "low", "medium", "high"
        """
        pass

    def calculate_vol_percentile(
        self,
        df: pd.DataFrame,
        current_vol: float,
        lookback: int = 252
    ) -> float:
        """Calculate current volatility percentile rank.

        Returns:
            Percentile in [0, 1] (0 = lowest vol in lookback, 1 = highest)
        """
        pass

    def calculate_distribution_moments(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> dict[str, float]:
        """Calculate return distribution moments.

        Returns:
            Dict with: {"skew": float, "kurtosis": float, "mean": float, "std": float}
        """
        pass
```

**Supported Factors:**
- **Realized Volatility:** Standard deviation of log returns (annualized)
- **Parkinson Volatility:** High-low range estimator (more efficient)
- **Volatility Regime:** Classification (low/medium/high based on percentile)
- **Volatility Percentile:** Current vol rank vs. historical
- **Skewness:** Return distribution asymmetry (negative = left tail risk)
- **Kurtosis:** Fat tails indicator (>3 = heavy tails)

**Files:**
- `strategies/factors/carry_volatility.py` (180 LOC)
- `tests/test_carry_volatility_calculator.py`

**Acceptance:**
- Realized vol matches standard pandas rolling std * sqrt(252)
- Parkinson vol uses high-low range formula correctly
- Regime detection uses percentile thresholds
- Vol percentile in [0, 1] range
- Skewness/kurtosis match scipy.stats calculations
- Test includes low/high volatility scenarios
- Performance: <12ms for 1000 bars
- `make fmt lint type test` green

---

### Phase 13.4 — Volume & Microstructure Factors 📋
**Status:** Planned
**Dependencies:** 13.3 (Carry & Volatility Factors)
**Task:** Implement volume and market microstructure factors

**Behavior:**
- Volume-weighted metrics (VWAP distance, volume profile)
- Order flow imbalance (buy/sell pressure)
- Liquidity metrics (bid-ask spread, depth)
- Trade intensity and clustering
- Price-volume correlation

**API:**
```python
class VolumeFlowCalculator:
    """Volume and order flow factor calculator."""

    def __init__(
        self,
        volume_lookback: int = 20
    ): ...

    def calculate_vwap_distance(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> pd.Series:
        """Calculate distance from VWAP.

        Formula: (close - VWAP) / VWAP

        Returns:
            Series of VWAP distance (negative = below VWAP)
        """
        pass

    def calculate_volume_profile(
        self,
        df: pd.DataFrame,
        lookback: int,
        bins: int = 10
    ) -> dict[str, Any]:
        """Calculate volume distribution by price level.

        Returns:
            Dict with:
                - "poc": float (Point of Control - price with most volume)
                - "value_area_high": float (top of 70% volume range)
                - "value_area_low": float (bottom of 70% volume range)
                - "profile": dict[float, float] (price bins → volume)
        """
        pass

    def calculate_order_flow_imbalance(
        self,
        trades_df: pd.DataFrame
    ) -> pd.Series:
        """Calculate buy/sell pressure from trades.

        Classify trades as buy/sell using tick rule:
        - Trade at ask or uptick → buy
        - Trade at bid or downtick → sell

        Formula: (buy_volume - sell_volume) / total_volume

        Returns:
            Series of order flow imbalance (-1 to +1)
        """
        pass

    def calculate_relative_volume(
        self,
        df: pd.DataFrame,
        lookback: int = 20
    ) -> pd.Series:
        """Calculate relative volume (current vs average).

        Formula: volume / volume_ma[lookback]

        Returns:
            Series of relative volume (1.0 = average, >1 = above average)
        """
        pass

    def calculate_price_volume_correlation(
        self,
        df: pd.DataFrame,
        lookback: int = 20
    ) -> pd.Series:
        """Calculate rolling correlation between price and volume.

        Positive correlation: volume follows price (healthy trend)
        Negative correlation: volume diverges from price (potential reversal)

        Returns:
            Series of correlation values (-1 to +1)
        """
        pass
```

**Supported Factors:**
- **VWAP Distance:** Price deviation from volume-weighted average price
- **Volume Profile:** Price levels with highest volume (POC, value area)
- **Order Flow Imbalance:** Buy vs sell pressure from trade classification
- **Relative Volume:** Current volume vs historical average
- **Price-Volume Correlation:** Relationship strength (trend confirmation)

**Files:**
- `strategies/factors/volume_flow.py` (220 LOC)
- `tests/test_volume_flow_calculator.py`

**Acceptance:**
- VWAP calculation uses cumulative sum (price*volume) / cumsum(volume)
- Volume profile identifies POC (point of control) correctly
- Order flow uses tick rule for trade classification
- Relative volume ratio (current / MA)
- Price-volume correlation uses pandas rolling correlation
- Test includes high/low volume scenarios
- Test verifies POC at price with most volume
- Performance: <18ms for 1000 bars
- `make fmt lint type test` green

---

### Phase 13.5 — ML Feature Engineering Pipeline 📋
**Status:** Planned
**Dependencies:** 13.4 (Volume & Microstructure Factors)
**Task:** Feature engineering pipeline for ML model inputs (offline training only)

**CRITICAL CONSTRAINTS:**
- **Offline Only:** No live model training/inference in production
- **Deterministic:** All features must be reproducible from historical data
- **No New Dependencies:** Use numpy/pandas (already in Phase 7 optional group)
  - **NO sklearn, statsmodels, or other ML libraries**
  - **Implement all scalers manually using numpy/pandas operations**
- **Version Control:** Feature pipeline versioned with config hash
- **No Look-Ahead Bias:** Features calculated from past data only (strict)
- **Runtime Guards:** Raise errors if pipeline used incorrectly (e.g., fit_transform in production)
- **No Network Calls:** All operations local (no external API calls)

**Behavior:**
- Combine multiple factor calculators into feature matrix
- Handle missing values (forward fill, interpolate, or drop)
- Feature scaling and normalization (manual implementations only)
- Lag feature generation (t-1, t-2, ... t-n)
- Rolling window statistics (mean, std, min, max)
- Feature importance tracking (for offline analysis)

**API:**
```python
from typing import Callable

@dataclass(frozen=True)
class FeatureConfig:
    """Feature engineering configuration."""
    feature_name: str
    calculator_type: Literal["momentum", "mean_reversion", "carry_vol", "volume_flow"]
    calculator_params: dict[str, Any]
    lag_periods: list[int]  # e.g., [1, 5, 10] for t-1, t-5, t-10
    enabled: bool
    version: str  # Semantic version for feature definition

@dataclass(frozen=True)
class FeatureMatrix:
    """Feature matrix output."""
    timestamp_ns: pd.DatetimeIndex  # Index
    features: pd.DataFrame  # Feature columns
    target: pd.Series | None  # Optional target for training
    metadata: dict[str, Any]  # Config hash, version, symbol, etc.

class FeaturePipeline:
    """ML feature engineering pipeline (offline use only)."""

    def __init__(
        self,
        config: list[FeatureConfig],
        scaling_method: Literal["standard", "minmax", "robust"] = "standard",
        enable_runtime_guards: bool = True
    ):
        """
        Args:
            scaling_method: Scaling method (implemented manually with numpy/pandas):
                - "standard": (x - mean) / std  (z-score normalization)
                - "minmax": (x - min) / (max - min)  (0-1 range)
                - "robust": (x - median) / IQR  (outlier-resistant)
            enable_runtime_guards: If True, raise errors on misuse (default: True)
        """
        ...

    def fit_transform(
        self,
        df: pd.DataFrame,
        target: pd.Series | None = None,
        allow_fit: bool = False
    ) -> FeatureMatrix:
        """Calculate features and fit scaler (OFFLINE TRAINING ONLY).

        Args:
            df: OHLCV DataFrame
            target: Optional target variable for supervised learning
            allow_fit: Must explicitly set to True (safety check)

        Returns:
            FeatureMatrix with scaled features

        Raises:
            RuntimeError: If allow_fit=False (prevents accidental use in production)

        Warning:
            This method fits scaling parameters. Only use during offline training.
        """
        if not allow_fit:
            raise RuntimeError(
                "fit_transform() is OFFLINE ONLY. "
                "Set allow_fit=True to confirm this is intentional. "
                "Never use in live trading or production services."
            )
        pass

    def transform(
        self,
        df: pd.DataFrame
    ) -> FeatureMatrix:
        """Calculate features using fitted scaler.

        Args:
            df: OHLCV DataFrame

        Returns:
            FeatureMatrix with scaled features (using fit params)

        Raises:
            ValueError: If scaler not fitted (must call fit_transform first)
        """
        if not self._scaler_fitted:
            raise ValueError(
                "Scaler not fitted. Call fit_transform() during offline training first."
            )
        pass

    def _standard_scale(
        self,
        values: pd.Series,
        fit: bool = False
    ) -> pd.Series:
        """Standard scaling (z-score): (x - mean) / std.

        Manual implementation using pandas operations (NO sklearn).

        Args:
            values: Input series
            fit: If True, calculate and store mean/std

        Returns:
            Scaled series
        """
        if fit:
            self._scale_params["mean"] = values.mean()
            self._scale_params["std"] = values.std()

        return (values - self._scale_params["mean"]) / self._scale_params["std"]

    def _minmax_scale(
        self,
        values: pd.Series,
        fit: bool = False
    ) -> pd.Series:
        """Min-max scaling: (x - min) / (max - min).

        Manual implementation using pandas operations (NO sklearn).

        Args:
            values: Input series
            fit: If True, calculate and store min/max

        Returns:
            Scaled series (0-1 range)
        """
        if fit:
            self._scale_params["min"] = values.min()
            self._scale_params["max"] = values.max()

        range_val = self._scale_params["max"] - self._scale_params["min"]
        return (values - self._scale_params["min"]) / range_val

    def _robust_scale(
        self,
        values: pd.Series,
        fit: bool = False
    ) -> pd.Series:
        """Robust scaling: (x - median) / IQR.

        Manual implementation using pandas operations (NO sklearn).
        More resistant to outliers than standard scaling.

        Args:
            values: Input series
            fit: If True, calculate and store median/IQR

        Returns:
            Scaled series
        """
        if fit:
            self._scale_params["median"] = values.median()
            q75 = values.quantile(0.75)
            q25 = values.quantile(0.25)
            self._scale_params["iqr"] = q75 - q25

        return (values - self._scale_params["median"]) / self._scale_params["iqr"]

    def add_lag_features(
        self,
        feature_df: pd.DataFrame,
        lags: list[int]
    ) -> pd.DataFrame:
        """Add lagged versions of features.

        Args:
            feature_df: Input features
            lags: List of lag periods (e.g., [1, 5, 10])

        Returns:
            DataFrame with original + lagged features
        """
        pass

    def calculate_rolling_stats(
        self,
        feature_df: pd.DataFrame,
        window: int,
        stats: list[str] = ["mean", "std", "min", "max"]
    ) -> pd.DataFrame:
        """Calculate rolling window statistics.

        Returns:
            DataFrame with rolling stat columns
        """
        pass

    def handle_missing_values(
        self,
        feature_df: pd.DataFrame,
        method: Literal["ffill", "interpolate", "drop"] = "ffill"
    ) -> pd.DataFrame:
        """Handle missing values in features."""
        pass

    def save_pipeline(
        self,
        path: Path
    ) -> None:
        """Save pipeline config and fitted scalers to disk.

        Serializes:
            - Feature config list
            - Fitted scaler parameters
            - Version and config hash
        """
        pass

    @classmethod
    def load_pipeline(
        cls,
        path: Path
    ) -> "FeaturePipeline":
        """Load pipeline from disk (for offline analysis/backtesting)."""
        pass
```

**Feature Engineering Patterns:**
1. **Base Features:** Raw factor values (momentum, mean reversion, etc.)
2. **Lag Features:** Historical values (t-1, t-5, t-10, t-20)
3. **Rolling Stats:** Moving average, std, min, max over window
4. **Interactions:** Product of two factors (e.g., momentum * volatility)
5. **Regime Indicators:** One-hot encoding of volatility/trend regime

**Files:**
- `strategies/ml/feature_pipeline.py` (300 LOC)
- `strategies/ml/contracts.py` (FeatureConfig, FeatureMatrix)
- `tests/test_feature_pipeline.py`

**Acceptance:**
- Feature calculation deterministic (same OHLCV → same features)
- **No look-ahead bias:** Features only use data up to timestamp t
- Lag features correctly shift (t-1 uses previous bar)
- **Manual scaler implementations** (NO sklearn/statsmodels):
  - Standard scaling: (x - mean) / std (pandas operations only)
  - Min-max scaling: (x - min) / (max - min) (pandas operations only)
  - Robust scaling: (x - median) / IQR (pandas quantile operations)
- **Runtime guards enforced:**
  - fit_transform() raises RuntimeError if allow_fit=False
  - transform() raises ValueError if scaler not fitted
  - Test verifies guards prevent misuse
- **No network calls:** All operations local (test verifies no HTTP/socket usage)
- Missing value handling configurable (ffill, interpolate, drop)
- Pipeline save/load preserves scaler state (JSON serialization, no pickle)
- Config hash tracks feature version
- Test verifies no future data leakage (feature[t] only depends on data[:t])
- Test includes save/load round-trip (pipeline state preserved)
- Test verifies manual scalers match expected mathematical formulas
- Performance: <50ms for 1000 bars with 20 features
- `make fmt lint type test` green

---

### Phase 13.6 — Factor Scoring Strategy 📋
**Status:** Planned
**Dependencies:** 13.5 (ML Feature Engineering Pipeline)
**Task:** Multi-factor scoring strategy using factor models

**Behavior:**
- Combine multiple factors into composite score
- Configurable factor weights (momentum: 0.4, mean reversion: 0.3, etc.)
- Threshold-based signal generation (score > threshold → buy, score < -threshold → sell)
- Regime-aware weighting (adjust weights based on volatility regime)
- Emit OrderIntent when signals trigger

**API:**
```python
from strategies.base import StrategyBase
from strategies.context import Context

class FactorScoringStrategy(StrategyBase):
    """Multi-factor scoring strategy."""

    def __init__(
        self,
        strategy_id: str,
        config: dict[str, Any]
    ):
        """
        Config schema:
            factors:
                - name: "momentum"
                  weight: 0.4
                  calculator: "MomentumCalculator"
                  params: {short_period: 10, medium_period: 30}
                - name: "mean_reversion"
                  weight: 0.3
                  ...
            signal_threshold: 0.6  # Composite score > 0.6 → signal
            regime_adjust: true  # Adjust weights by volatility regime
            position_size_pct: 0.02  # 2% of portfolio per signal
        """
        super().__init__(strategy_id, config)
        self._factor_calculators = self._initialize_calculators()
        self._weights = self._load_factor_weights()

    async def on_event(
        self,
        event_type: str,
        event: dict[str, Any],
        ctx: Context
    ) -> None:
        """Handle market data events.

        Flow:
            1. Receive OHLCV bar (event_type="md.ohlcv")
            2. Calculate all factors
            3. Compute composite score
            4. Adjust for regime if enabled
            5. Check threshold
            6. Emit OrderIntent if signal triggered
        """
        pass

    def calculate_composite_score(
        self,
        factor_values: dict[str, FactorValue],
        weights: dict[str, float]
    ) -> FactorScore:
        """Calculate weighted composite factor score.

        Args:
            factor_values: Dict of {factor_name: FactorValue}
            weights: Dict of {factor_name: weight}

        Returns:
            FactorScore with composite_score and signal_strength
        """
        pass

    def adjust_weights_for_regime(
        self,
        weights: dict[str, float],
        regime: str
    ) -> dict[str, float]:
        """Adjust factor weights based on volatility regime.

        Logic:
            - High vol regime: Increase mean reversion weight, decrease momentum
            - Low vol regime: Increase momentum weight, decrease mean reversion
            - Trending regime: Increase momentum weight

        Returns:
            Adjusted weights (still sum to 1.0)
        """
        pass

    def generate_signal(
        self,
        score: FactorScore,
        threshold: float
    ) -> Literal["buy", "sell", "neutral"]:
        """Generate trading signal from score.

        Args:
            score: Composite factor score
            threshold: Signal threshold (e.g., 0.6)

        Returns:
            "buy" if score > threshold
            "sell" if score < -threshold
            "neutral" otherwise
        """
        pass
```

**Signal Generation Logic:**
```python
# Example
composite_score = 0.4*momentum + 0.3*mean_reversion + 0.3*volume_flow

if composite_score > signal_threshold:
    # Strong buy signal
    emit OrderIntent(side="buy", quantity=position_size)
elif composite_score < -signal_threshold:
    # Strong sell signal
    emit OrderIntent(side="sell", quantity=position_size)
else:
    # No signal
    pass
```

**Files:**
- `strategies/samples/factor_scoring.py` (250 LOC)
- `config/strategies/factor_scoring.yaml` (example config)
- `tests/test_factor_scoring_strategy.py`

**Acceptance:**
- Composite score calculation matches weighted sum of standardized factors
- Regime-aware weighting adjusts correctly (test low/high vol scenarios)
- Signal threshold enforced (no signal if |score| < threshold)
- OrderIntent emitted only when signal crosses threshold
- Position sizing configurable (% of portfolio)
- Test includes multi-symbol scenario (separate scores per symbol)
- Test verifies no signals when all factors neutral
- Strategy registered in registry (auto-discovery)
- `make fmt lint type test` green

---

### Phase 13.7 — Statistical Arbitrage Strategy 📋
**Status:** Planned
**Dependencies:** 13.6 (Factor Scoring Strategy)
**Task:** Pairs trading / statistical arbitrage strategy

**Behavior:**
- Identify cointegrated pairs (offline analysis, config-driven)
- Calculate z-score of price spread
- Enter mean reversion trades when spread extreme
- Exit when spread reverts to mean
- Support multiple pairs simultaneously

**API:**
```python
from strategies.base import StrategyBase

class StatArbStrategy(StrategyBase):
    """Statistical arbitrage (pairs trading) strategy."""

    def __init__(
        self,
        strategy_id: str,
        config: dict[str, Any]
    ):
        """
        Config schema:
            pairs:
                - symbol_a: "ATOM/USDT"
                  symbol_b: "OSMO/USDT"
                  hedge_ratio: 1.2  # Pre-calculated from cointegration
                  zscore_entry: 2.0  # Enter when |zscore| > 2.0
                  zscore_exit: 0.5   # Exit when |zscore| < 0.5
                  lookback: 100      # Lookback for spread mean/std
            position_size_pct: 0.05
        """
        super().__init__(strategy_id, config)
        self._pairs = self._load_pairs()
        self._spread_history: dict[str, deque] = {}  # Rolling spread values

    async def on_event(
        self,
        event_type: str,
        event: dict[str, Any],
        ctx: Context
    ) -> None:
        """Handle market data events for both legs.

        Flow:
            1. Receive price updates for symbol_a and symbol_b
            2. Calculate spread: price_a - hedge_ratio * price_b
            3. Calculate z-score of spread
            4. Check entry/exit conditions
            5. Emit OrderIntent for both legs (long one, short other)
        """
        pass

    def calculate_spread(
        self,
        price_a: float,
        price_b: float,
        hedge_ratio: float
    ) -> float:
        """Calculate price spread.

        Formula: price_a - hedge_ratio * price_b
        """
        pass

    def calculate_spread_zscore(
        self,
        current_spread: float,
        spread_history: deque[float],
        lookback: int
    ) -> float:
        """Calculate z-score of current spread.

        Formula: (current_spread - mean(spread_history)) / std(spread_history)
        """
        pass

    def check_entry_signal(
        self,
        zscore: float,
        zscore_threshold: float,
        current_position: dict[str, float]
    ) -> Literal["long_a_short_b", "long_b_short_a", "none"]:
        """Check if entry condition met.

        Logic:
            - If zscore > +threshold and no position: long A, short B (spread too high)
            - If zscore < -threshold and no position: long B, short A (spread too low)

        Returns:
            Entry signal or "none"
        """
        pass

    def check_exit_signal(
        self,
        zscore: float,
        zscore_exit: float,
        current_position: dict[str, float]
    ) -> bool:
        """Check if exit condition met.

        Logic:
            - If |zscore| < zscore_exit and have position: close both legs

        Returns:
            True if should exit
        """
        pass
```

**Entry/Exit Logic:**
```python
# Entry
if zscore > 2.0 and no_position:
    # Spread too high → mean revert down expected
    # Long A (buy), Short B (sell)
    emit OrderIntent(symbol=A, side="buy", qty=position_size)
    emit OrderIntent(symbol=B, side="sell", qty=position_size * hedge_ratio)

if zscore < -2.0 and no_position:
    # Spread too low → mean revert up expected
    # Short A (sell), Long B (buy)
    emit OrderIntent(symbol=A, side="sell", qty=position_size)
    emit OrderIntent(symbol=B, side="buy", qty=position_size * hedge_ratio)

# Exit
if abs(zscore) < 0.5 and have_position:
    # Spread reverted → close both legs
    emit OrderIntent(symbol=A, side=opposite_of_entry, qty=position_size)
    emit OrderIntent(symbol=B, side=opposite_of_entry, qty=position_size * hedge_ratio)
```

**Files:**
- `strategies/samples/stat_arb.py` (280 LOC)
- `config/strategies/stat_arb.yaml` (example config with pairs)
- `tests/test_stat_arb_strategy.py`

**Acceptance:**
- Spread calculation correct (price_a - hedge_ratio * price_b)
- Z-score uses rolling mean/std of spread history
- Entry signals only trigger when no position
- Exit signals only trigger when have position
- Both legs emit OrderIntent simultaneously (atomic pair trade)
- Hedge ratio applied correctly (maintains dollar neutrality)
- Test includes full cycle: entry → spread reverts → exit
- Test verifies no entry if already in position
- Strategy registered in registry
- `make fmt lint type test` green

---

### Phase 13.8 — Ensemble Meta-Strategy 📋
**Status:** Planned
**Dependencies:** 13.7 (Statistical Arbitrage Strategy)
**Task:** Meta-strategy that combines signals from multiple sub-strategies

**Behavior:**
- Aggregate signals from multiple child strategies
- Voting mechanism (majority vote, weighted vote)
- Conflict resolution (what if strategies disagree?)
- Position sizing based on signal strength/agreement
- Monitor child strategy performance and adjust weights

**API:**
```python
from strategies.base import StrategyBase

class EnsembleMetaStrategy(StrategyBase):
    """Ensemble meta-strategy combining multiple sub-strategies."""

    def __init__(
        self,
        strategy_id: str,
        config: dict[str, Any]
    ):
        """
        Config schema:
            child_strategies:
                - strategy_id: "momentum_v1"
                  weight: 0.4
                  enabled: true
                - strategy_id: "mean_reversion_v1"
                  weight: 0.3
                  enabled: true
                - strategy_id: "factor_scoring_v1"
                  weight: 0.3
                  enabled: true
            aggregation_method: "weighted_vote"  # or "majority_vote", "unanimous"
            min_agreement: 0.6  # Require 60% agreement to emit signal
            position_size_pct: 0.03
        """
        super().__init__(strategy_id, config)
        self._child_strategies = self._load_children()
        self._signal_buffer: dict[str, list[dict]] = {}  # Buffer child signals

    async def on_event(
        self,
        event_type: str,
        event: dict[str, Any],
        ctx: Context
    ) -> None:
        """Handle events and coordinate child strategies.

        Flow:
            1. Forward event to all child strategies
            2. Collect signals from children (via bus topic "ensemble.signals.{child_id}")
            3. Aggregate signals using configured method
            4. Check agreement threshold
            5. Emit final OrderIntent if consensus reached
        """
        pass

    def aggregate_signals_weighted_vote(
        self,
        child_signals: dict[str, dict[str, Any]],
        weights: dict[str, float]
    ) -> dict[str, Any]:
        """Aggregate using weighted voting.

        Args:
            child_signals: {strategy_id: {"side": "buy", "confidence": 0.8, ...}}
            weights: {strategy_id: weight}

        Returns:
            Aggregated signal:
                {
                    "side": "buy"|"sell"|"neutral",
                    "confidence": float (0-1),
                    "agreement_score": float (0-1)
                }

        Logic:
            - Calculate weighted sum of (side * confidence * weight)
            - Positive sum → buy, negative → sell, ~zero → neutral
            - Agreement score = |weighted_sum| / sum(weights)
        """
        pass

    def aggregate_signals_majority_vote(
        self,
        child_signals: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Aggregate using majority voting (ignore weights).

        Returns:
            Side with most votes, confidence = vote_ratio
        """
        pass

    def aggregate_signals_unanimous(
        self,
        child_signals: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Require all children agree (strictest).

        Returns:
            Signal only if all children agree on same side
        """
        pass

    def calculate_position_size(
        self,
        base_size: float,
        agreement_score: float
    ) -> float:
        """Scale position size by agreement strength.

        Args:
            base_size: Base position size
            agreement_score: Agreement score (0-1)

        Returns:
            Scaled position size (higher agreement → larger size)
        """
        pass

    async def monitor_child_performance(
        self,
        ctx: Context
    ) -> dict[str, float]:
        """Monitor child strategy performance and adjust weights.

        OFFLINE ONLY: This should run as separate analysis, not in live trading.

        Returns:
            Dict of {strategy_id: performance_score}
        """
        pass
```

**Aggregation Methods:**

1. **Weighted Vote:**
   - Each child vote weighted by configured weight
   - Final signal = sign(sum(weight * signal * confidence))
   - Agreement = |sum| / sum(weights)

2. **Majority Vote:**
   - Count votes (ignore weights)
   - Side with >50% votes wins
   - Agreement = vote_ratio

3. **Unanimous:**
   - All children must agree
   - Agreement = 1.0 if all agree, 0.0 otherwise

**Files:**
- `strategies/samples/ensemble_meta.py` (320 LOC)
- `config/strategies/ensemble_meta.yaml` (example config)
- `tests/test_ensemble_meta_strategy.py`

**Acceptance:**
- Weighted vote calculation correct (weighted sum of signals)
- Majority vote counts correctly (>50% determines side)
- Unanimous requires all children same side
- Agreement threshold enforced (no signal if below min_agreement)
- Position sizing scales with agreement (higher agreement → larger size)
- Test includes 3-child scenario with disagreement (2 buy, 1 sell)
- Test verifies unanimous blocks signal if any child disagrees
- Test includes all aggregation methods
- Child signals collected via bus subscription
- Strategy registered in registry
- `make fmt lint type test` green

---

### Phase 13.9 — Regime-Adaptive Strategy 📋
**Status:** Planned
**Dependencies:** 13.8 (Ensemble Meta-Strategy)
**Task:** Strategy that adapts behavior based on market regime

**Behavior:**
- Detect market regime (trending, mean-reverting, volatile, neutral)
- Switch strategy logic based on regime
- Use different factors/weights per regime
- Historical regime classification for validation
- Smooth regime transitions (hysteresis to avoid flapping)

**API:**
```python
from strategies.base import StrategyBase
from strategies.factors.carry_volatility import CarryVolatilityCalculator

class RegimeAdaptiveStrategy(StrategyBase):
    """Adaptive strategy that switches logic based on market regime."""

    def __init__(
        self,
        strategy_id: str,
        config: dict[str, Any]
    ):
        """
        Config schema:
            regime_detection:
                method: "volatility_percentile"  # or "trend_strength", "hybrid"
                lookback: 100
                thresholds:
                    low_vol: 0.33  # Percentile cutoffs
                    high_vol: 0.67
                hysteresis: 0.1  # Prevent flapping (10% buffer)

            regime_strategies:
                trending:
                    factors: ["momentum", "trend_strength"]
                    weights: {"momentum": 0.7, "trend_strength": 0.3}
                    signal_threshold: 0.5
                mean_reverting:
                    factors: ["zscore", "rsi_divergence"]
                    weights: {"zscore": 0.6, "rsi_divergence": 0.4}
                    signal_threshold: 0.6
                volatile:
                    factors: []  # No trading in high vol
                    weights: {}
                    signal_threshold: 1.0  # Effectively disabled
                neutral:
                    factors: ["momentum", "zscore"]
                    weights: {"momentum": 0.5, "zscore": 0.5}
                    signal_threshold: 0.7
        """
        super().__init__(strategy_id, config)
        self._regime_detector = self._initialize_regime_detector()
        self._current_regime: str = "neutral"
        self._regime_history: deque = deque(maxlen=100)

    async def on_event(
        self,
        event_type: str,
        event: dict[str, Any],
        ctx: Context
    ) -> None:
        """Handle market data and adapt to regime.

        Flow:
            1. Receive OHLCV data
            2. Detect current regime
            3. Check for regime change (with hysteresis)
            4. Load regime-specific config (factors, weights, threshold)
            5. Calculate factors for current regime
            6. Generate signal using regime logic
            7. Emit OrderIntent if signal triggered
        """
        pass

    def detect_regime(
        self,
        df: pd.DataFrame,
        method: str,
        thresholds: dict[str, float]
    ) -> str:
        """Detect current market regime.

        Args:
            df: OHLCV DataFrame
            method: "volatility_percentile", "trend_strength", or "hybrid"
            thresholds: Percentile cutoffs for regime classification

        Returns:
            Regime label: "trending", "mean_reverting", "volatile", "neutral"
        """
        pass

    def check_regime_change(
        self,
        new_regime: str,
        current_regime: str,
        hysteresis: float
    ) -> str:
        """Check if regime change should trigger (with hysteresis).

        Args:
            new_regime: Newly detected regime
            current_regime: Current active regime
            hysteresis: Buffer percentage (e.g., 0.1 = 10% buffer)

        Returns:
            Regime to use (may stay as current_regime if within hysteresis)

        Logic:
            - If new_regime == current_regime: no change
            - If regime metric beyond hysteresis buffer: change
            - Otherwise: stay in current_regime (prevent flapping)
        """
        pass

    def load_regime_config(
        self,
        regime: str
    ) -> dict[str, Any]:
        """Load strategy config for specific regime.

        Returns:
            Dict with factors, weights, signal_threshold for regime
        """
        pass

    def log_regime_transition(
        self,
        old_regime: str,
        new_regime: str,
        timestamp_ns: int,
        ctx: Context
    ) -> None:
        """Log regime change to journal.

        Emits to bus topic: "strategy.regime_change.{strategy_id}"
        """
        pass
```

**Regime Detection Methods:**

1. **Volatility Percentile:**
   - Low vol (< 33rd percentile) → Trending regime (momentum works)
   - Medium vol (33-67) → Neutral regime (mixed strategies)
   - High vol (> 67th percentile) → Volatile regime (reduce/stop trading)

2. **Trend Strength:**
   - High R² (> 0.7) → Trending regime
   - Low R² (< 0.3) → Mean-reverting regime
   - Medium R² → Neutral

3. **Hybrid:**
   - Combine volatility + trend strength
   - Matrix of (vol_regime, trend_regime) → final regime

**Hysteresis Logic:**
```python
# Prevent flapping between regimes
if new_regime != current_regime:
    # Check if signal strong enough to overcome hysteresis
    regime_metric_change = abs(new_metric - old_metric)
    if regime_metric_change > hysteresis_threshold:
        # Strong signal → change regime
        return new_regime
    else:
        # Weak signal → stay in current regime
        return current_regime
```

**Files:**
- `strategies/samples/regime_adaptive.py` (350 LOC)
- `config/strategies/regime_adaptive.yaml`
- `tests/test_regime_adaptive_strategy.py`

**Acceptance:**
- Regime detection uses volatility percentile correctly
- Trend strength regime uses R² from linear regression
- Hysteresis prevents regime flapping (test rapid regime oscillation)
- Regime-specific factors loaded correctly
- Signal threshold varies by regime
- Test includes regime transition (trending → mean_reverting)
- Test verifies hysteresis keeps regime stable within buffer
- Volatile regime stops trading (signal_threshold = 1.0)
- Regime changes logged to bus and journal
- Strategy registered in registry
- `make fmt lint type test` green

---

### Phase 13.10 — Advanced Strategy Documentation 📋
**Status:** Planned
**Dependencies:** 13.9 (Regime-Adaptive Strategy)
**Task:** Comprehensive documentation for advanced strategy toolkit

**Deliverables:**

**1. Factor Model Guide (docs/strategies/FACTOR_MODELS.md)**
- Overview of factor-based investing
- Supported factor categories (momentum, mean reversion, carry, volume)
- Factor calculation details (formulas, lookback periods)
- Factor standardization (z-score, percentile)
- Composite scoring methodology
- Example factor configs

**2. ML Feature Engineering Guide (docs/strategies/ML_FEATURES.md)**
- Feature pipeline architecture
- **Offline-only constraint explanation** (no live training/inference)
- **Avoiding look-ahead bias** (critical - features at time t only use data[:t])
- **Manual scaler implementations** (NO sklearn - use pandas/numpy only)
  - Standard scaling formula: (x - mean) / std
  - Min-max scaling formula: (x - min) / (max - min)
  - Robust scaling formula: (x - median) / IQR
- **Runtime guard enforcement** (fit_transform requires explicit allow_fit=True)
- **No network calls** (all operations local, no external APIs)
- Feature versioning and config hash
- Lag feature generation (t-1, t-5, t-10, etc.)
- Rolling window statistics (mean, std, min, max)
- Save/load pipeline for backtesting (JSON only, no pickle)
- Example feature engineering workflow

**3. Strategy Recipes (docs/strategies/RECIPES.md)**
- Factor Scoring Strategy: Multi-factor scoring with regime adjustment
- Statistical Arbitrage: Pairs trading with cointegration
- Ensemble Meta-Strategy: Combining multiple strategies
- Regime-Adaptive Strategy: Switching logic by market regime
- Configuration examples for each
- Backtesting setup
- Performance expectations

**4. Factor Library Reference (docs/strategies/FACTOR_LIBRARY.md)**
- Complete list of implemented factors
- API reference for each calculator
- Input requirements (OHLCV, trades, etc.)
- Output format (FactorValue, FactorScore)
- Performance characteristics
- Example usage code

**5. Strategy Development Guide (docs/strategies/DEVELOPMENT.md)**
- How to create new factor calculators
- How to build custom strategies using factors
- Testing requirements (determinism, no look-ahead)
- Integration with existing framework (StrategyBase, Context)
- Risk engine integration (OrderIntent flow)
- Debugging tips (logging, visualization)

**6. API Reference (docs/strategies/API.md)**
- FactorValue, FactorScore, FactorConfig contracts
- FeaturePipeline API
- MomentumCalculator API
- MeanReversionCalculator API
- CarryVolatilityCalculator API
- VolumeFlowCalculator API
- All strategy classes API

**Files:**
- `docs/strategies/FACTOR_MODELS.md` (600 words)
- `docs/strategies/ML_FEATURES.md` (800 words)
- `docs/strategies/RECIPES.md` (1000 words)
- `docs/strategies/FACTOR_LIBRARY.md` (500 words)
- `docs/strategies/DEVELOPMENT.md` (700 words)
- `docs/strategies/API.md` (400 words)

**Acceptance:**
- Factor model guide explains all factor types with formulas
- ML features guide emphasizes offline-only and no look-ahead bias
- Strategy recipes include complete config examples
- Factor library documents all calculators with API examples
- Development guide includes step-by-step new strategy creation
- API reference covers all public interfaces
- All docs use consistent markdown formatting
- Code examples are syntactically correct (Python code blocks)
- Cross-references between docs work correctly
- `make fmt lint type test` green (no code changes, but run anyway)

---
