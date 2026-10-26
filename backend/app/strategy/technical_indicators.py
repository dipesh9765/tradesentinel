"""
Technical Indicators & Quantitative Signal Metrics - TradeSentinel

This module implements institutional-grade intraday technical indicators used
for momentum, trend, volatility, and mean-reversion analysis on equity & derivative
time-series data.

Implemented Indicators:
1. Exponential Moving Average (EMA 9, 21, 50, 200) - Trend tracking and ribbon dynamics.
2. Relative Strength Index (RSI 14) - Oscillator with momentum divergence detection.
3. Volume Weighted Average Price (VWAP & SD Bands) - Benchmark for institutional execution.
4. Average True Range (ATR 14) - Volatility measure for dynamic stop-loss & targets.
5. Supertrend (10, 3.0) - Institutional trend-following and trailing stop baseline.
6. Average Directional Index (ADX 14, +DI, -DI) - Trend strength & sideways chop filter.
7. Central Pivot Range (CPR - TC, Pivot, BC) - Indian intraday floor roadmap.
8. Classic Floor Pivot Points (R1, R2, S1, S2) - Structural intraday support/resistance.
9. Bollinger Bands (20, 2.0) - Mean-reversion boundaries.
"""

from typing import Any

import numpy as np
import pandas as pd


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculates the Exponential Moving Average (EMA) for a price series.

    Formula:
        EMA_t = (Price_t * alpha) + (EMA_{t-1} * (1 - alpha))
        where alpha = 2 / (period + 1)
    """
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculates the Relative Strength Index (RSI) momentum oscillator.

    Formula:
        RSI = 100 - [100 / (1 + RS)]
        where RS = Average Gain / Average Loss over the specified period.
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()

    rs = gain / loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _session_key(df: pd.DataFrame) -> pd.Series:
    """Trading-day label per bar so cumulative indicators restart each session."""
    if "timestamp" in df.columns:
        try:
            return pd.to_datetime(df["timestamp"]).dt.date
        except Exception:
            pass
    return pd.Series(0, index=df.index)


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculates the intraday Volume Weighted Average Price (VWAP), restarting every trading day.

    Formula:
        Typical Price (TP) = (High + Low + Close) / 3
        VWAP = Cumulative Sum(TP * Volume) / Cumulative Sum(Volume)   (per session)
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    key = _session_key(df)
    cum_vol = df["volume"].groupby(key).cumsum()
    cum_pv = (typical_price * df["volume"]).groupby(key).cumsum()
    vwap = cum_pv / cum_vol.replace(0, np.nan)
    return vwap.groupby(key).transform(lambda s: s.bfill().ffill()).ffill().bfill()


def calculate_vwap_bands(df: pd.DataFrame, num_std: float = 1.5) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculates intraday VWAP along with Upper and Lower standard deviation bands (per session).
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    key = _session_key(df)
    vwap = calculate_vwap(df)
    cum_vol = df["volume"].groupby(key).cumsum()
    weighted = ((typical_price - vwap) ** 2 * df["volume"]).groupby(key).cumsum()
    variance = weighted / cum_vol.replace(0, np.nan)
    std_dev = np.sqrt(variance).fillna(0.0)
    upper_band = vwap + (std_dev * num_std)
    lower_band = vwap - (std_dev * num_std)
    return vwap, upper_band, lower_band


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculates the Average True Range (ATR) volatility metric.
    """
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.bfill()


def calculate_bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculates Bollinger Bands (Upper Band, Middle Band / SMA, Lower Band).
    """
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, sma, lower


def calculate_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """
    Calculates the Supertrend indicator (Value and Trend Direction).

    Args:
        df: DataFrame with 'high', 'low', 'close'.
        period: ATR calculation period (default 10).
        multiplier: Multiplier factor for ATR band (default 3.0).

    Returns:
        Tuple of (supertrend_value_series, direction_series)
        where direction is 1 (BULLISH) and -1 (BEARISH).
    """
    atr = calculate_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0

    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    n = len(df)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    supertrend = np.zeros(n)
    direction = np.ones(n, dtype=int)  # 1 = Bullish, -1 = Bearish

    close = df["close"].values
    b_upper = basic_upper.values
    b_lower = basic_lower.values

    for i in range(1, n):
        # Upper band adjustment
        if b_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = b_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Lower band adjustment
        if b_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = b_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Trend direction logic
        if supertrend[i - 1] == final_upper[i - 1]:
            if close[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]
        else:
            if close[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]

    if n > 0 and supertrend[0] == 0:
        supertrend[0] = final_lower[0] if direction[0] == 1 else final_upper[0]

    return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)


def calculate_adx(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculates the Average Directional Index (ADX) and Directional Indicators (+DI, -DI).
    Used to filter out choppy/sideways markets (ADX < 20) vs strong trends (ADX > 22).

    Returns:
        Tuple of (adx_series, plus_di_series, minus_di_series).
    """
    high = df["high"]
    low = df["low"]
    tr = calculate_atr(df, period=1)  # 1-period TR
    smoothed_tr = tr.rolling(window=period).sum().replace(0, np.nan)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    smoothed_plus_dm = pd.Series(plus_dm, index=df.index).rolling(window=period).sum()
    smoothed_minus_dm = pd.Series(minus_dm, index=df.index).rolling(window=period).sum()

    plus_di = (smoothed_plus_dm / smoothed_tr) * 100.0
    minus_di = (smoothed_minus_dm / smoothed_tr) * 100.0

    di_diff = (plus_di - minus_di).abs()
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = (di_diff / di_sum) * 100.0

    adx = dx.rolling(window=period).mean().fillna(20.0)
    return adx, plus_di.fillna(0.0), minus_di.fillna(0.0)


def calculate_cpr(high: float, low: float, close: float) -> dict[str, Any]:
    """
    Calculates Central Pivot Range (CPR - Pivot, Bottom Central, Top Central)
    and classifies the daily market regime.

    Formulas:
        Pivot = (High + Low + Close) / 3
        Bottom Central (BC) = (High + Low) / 2
        Top Central (TC) = (Pivot - BC) + Pivot
        CPR Width % = |TC - BC| / Pivot * 100

    Regime Classification:
        - Narrow CPR (Width < 0.25%): High probability Trend Day (Breakout Strategy).
        - Average CPR (0.25% - 0.50%): Normal Volatility.
        - Wide CPR (Width > 0.50%): High probability Range-Bound/Choppy Day (Support/Resistance Bounce).
    """
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (pivot - bc) + pivot

    cpr_top = max(tc, bc)
    cpr_bottom = min(tc, bc)
    cpr_width = abs(tc - bc)
    cpr_width_pct = (cpr_width / pivot) * 100.0 if pivot > 0 else 0.0

    if cpr_width_pct < 0.25:
        regime = "NARROW_TRENDING"
    elif cpr_width_pct > 0.50:
        regime = "WIDE_RANGE_BOUND"
    else:
        regime = "AVERAGE_NORMAL"

    return {
        "pivot": round(pivot, 2),
        "bc": round(bc, 2),
        "tc": round(tc, 2),
        "cpr_top": round(cpr_top, 2),
        "cpr_bottom": round(cpr_bottom, 2),
        "cpr_width": round(cpr_width, 2),
        "cpr_width_pct": round(cpr_width_pct, 3),
        "cpr_regime": regime,
    }


def calculate_pivot_points(high: float, low: float, close: float) -> dict[str, float]:
    """
    Calculates Classic Floor Pivot Points and support/resistance levels.
    """
    pp = (high + low + close) / 3.0
    r1 = 2.0 * pp - low
    s1 = 2.0 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    return {
        "pivot": round(pp, 2),
        "r1": round(r1, 2),
        "s1": round(s1, 2),
        "r2": round(r2, 2),
        "s2": round(s2, 2),
    }


def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 14) -> str:
    """
    Detects classic Bullish or Bearish RSI momentum divergence in recent candles.
    """
    if len(df) < lookback + 2:
        return "NONE"

    recent = df.tail(lookback)
    price_low_idx = recent["low"].idxmin()
    price_high_idx = recent["high"].idxmax()
    curr_low = df["low"].iloc[-1]
    curr_high = df["high"].iloc[-1]
    curr_rsi = df.get("rsi_14", pd.Series([50])).iloc[-1]

    lowest_candle = recent.loc[price_low_idx]
    highest_candle = recent.loc[price_high_idx]

    # Bullish Divergence: Price lower or equal, but RSI higher
    if (
        curr_low <= lowest_candle["low"]
        and curr_rsi > (lowest_candle.get("rsi_14", 50) + 3.0)
        and curr_rsi < 45
    ):
        return "BULLISH_DIVERGENCE"

    # Bearish Divergence: Price higher or equal, but RSI lower
    if (
        curr_high >= highest_candle["high"]
        and curr_rsi < (highest_candle.get("rsi_14", 50) - 3.0)
        and curr_rsi > 55
    ):
        return "BEARISH_DIVERGENCE"

    return "NONE"


def enrich_candle_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches raw OHLCV candle records with complete intraday quantitative indicators.
    Calculates EMA (9, 21, 50, 200), RSI 14, cumulative VWAP & Bands, ATR 14,
    Bollinger Bands, Supertrend (10, 3), and ADX (14).
    """
    df = df.copy()
    if len(df) == 0:
        return df

    df["ema_9"] = calculate_ema(df["close"], 9)
    df["ema_21"] = calculate_ema(df["close"], 21)
    df["ema_50"] = calculate_ema(df["close"], 50)
    df["ema_200"] = calculate_ema(df["close"], 200) if len(df) >= 200 else calculate_ema(df["close"], 50)
    df["rsi_14"] = calculate_rsi(df["close"], 14)

    vwap, vwap_upper, vwap_lower = calculate_vwap_bands(df, num_std=1.5)
    df["vwap"] = vwap
    df["vwap_upper"] = vwap_upper
    df["vwap_lower"] = vwap_lower
    df["atr_14"] = calculate_atr(df, 14)

    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(df["close"])
    df["bb_upper"] = bb_upper
    df["bb_middle"] = bb_mid
    df["bb_lower"] = bb_lower

    st_val, st_dir = calculate_supertrend(df, period=10, multiplier=3.0)
    df["supertrend"] = st_val
    df["supertrend_direction"] = st_dir

    adx, plus_di, minus_di = calculate_adx(df, period=14)
    df["adx_14"] = adx
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    return df
