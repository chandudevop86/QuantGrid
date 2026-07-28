from __future__ import annotations

from typing import Any

import pandas as pd
import numpy as np

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def prepare_ohlcv(data: Any) -> pd.DataFrame:
    df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    df.columns = [str(column).strip().lower() for column in df.columns]
    rename_map = {
        "datetime": "timestamp",
        "date": "timestamp",
        "time": "timestamp",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "vol": "volume",
    }
    for source, target in rename_map.items():
        if source in df.columns and target not in df.columns:
            df = df.rename(columns={source: target})

    missing = [column for column in OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    df = df.loc[:, OHLCV_COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return (
        df.dropna(subset=["timestamp", "open", "high", "low", "close","volume"])
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )




def add_core_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    # ------------------------------------------------------------------
    # Candle metrics
    # ------------------------------------------------------------------
    out["bar_range"] = (out["high"] - out["low"]).clip(lower=0.0)
    out["body_size"] = (out["close"] - out["open"]).abs()

    out["candle_body_ratio"] = (
        out["body_size"]
        / out["bar_range"].replace(0, np.nan)
    ).fillna(0)


    
    # ------------------------------------------------------------------
    # RSI
    # ------------------------------------------------------------------
    out["rsi"] = rsi(out["close"], 14)

    out["rsi_overbought"] = out["rsi"] >= 70
    out["rsi_oversold"] = out["rsi"] <= 30

    # ------------------------------------------------------------------
    # Session VWAP
    # ------------------------------------------------------------------
    out["session_day"] = out["timestamp"].dt.strftime("%Y-%m-%d")
    out["vwap"] = session_vwap(out)

    out["above_vwap"] = out["close"] > out["vwap"]
    out["below_vwap"] = out["close"] < out["vwap"]

    # ------------------------------------------------------------------
    # ATR / ADX
    # ------------------------------------------------------------------
    out["atr_14"] = atr(out, 14)
    out = out.join(adx(out, 14))

    out["strong_trend"] = out["adx"] >= 25

    out["atr_pct"] = (
        out["atr_14"]
        / out["close"].replace(0, np.nan)
        * 100
    ).fillna(0)

    

    
    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------
    out["avg_volume_20"] = (
        out["volume"]
        .rolling(20, min_periods=1)
        .mean()
    )

    out["volume_ratio"] = (
        out["volume"]
        /
        out["avg_volume_20"].replace(0, np.nan)
    ).fillna(0)

    out["volume_spike"] = out["volume_ratio"] >= 1.5

    # ------------------------------------------------------------------
    # Range / Breakout
    # ------------------------------------------------------------------
    out["avg_range_5"] = (
        out["bar_range"]
        .rolling(5, min_periods=1)
        .mean()
    )

    out["recent_high"] = (
        out["high"]
        .shift(1)
        .rolling(6, min_periods=2)
        .max()
    )

    out["recent_low"] = (
        out["low"]
        .shift(1)
        .rolling(6, min_periods=2)
        .min()
    )

    out["breakout_up"] = out["close"] > out["recent_high"]
    out["breakout_down"] = out["close"] < out["recent_low"]

    # ------------------------------------------------------------------
    # Fair Value Gaps
    # ------------------------------------------------------------------
    out["bullish_fvg_gap"] = (
        out["low"]
        - out["high"].shift(2)
    ).clip(lower=0.0)

    out["bearish_fvg_gap"] = (
        out["low"].shift(2)
        - out["high"]
    ).clip(lower=0.0)

    # ------------------------------------------------------------------
    # Large candle
    # ------------------------------------------------------------------
    out["large_body"] = out["candle_body_ratio"] >= 0.60
    

# ------------------------------------------------------------------
# EMAs
# ------------------------------------------------------------------
    out["ema_9"] = ema(out["close"], 9)
    out["ema_12"] = ema(out["close"], 12)
    out["ema_21"] = ema(out["close"], 21)
    out["ema_26"] = ema(out["close"], 26)
    out["ema_50"] = ema(out["close"], 50)
    out["ema_200"] = ema(out["close"], 200)

# ------------------------------------------------------------------
# Standard MACD (12,26,9)
# ------------------------------------------------------------------
    out["ema_12"] = ema(out["close"], 12)
    out["ema_26"] = ema(out["close"], 26)

    out["macd"] = out["ema_12"] - out["ema_26"]
    out["macd_signal"] = ema(out["macd"], 9)
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    out["macd_bullish"] = out["macd"] > out["macd_signal"]
    out["macd_bearish"] = out["macd"] < out["macd_signal"]

    # ------------------------------------------------------------------
    # EMA Spread
    # ------------------------------------------------------------------
    out["ema_spread"] = (
        (
            out["ema_50"] - out["ema_200"]
        )
        /
        out["close"].replace(0, np.nan)
    ).fillna(0)

    # ------------------------------------------------------------------
    # Trend Direction
    # ------------------------------------------------------------------
    out["trend"] = np.select(
        [
            out["ema_50"] > out["ema_200"],
            out["ema_50"] < out["ema_200"],
        ],
        [
            "bullish",
            "bearish",
        ],
        default="sideways",
    )

    # ------------------------------------------------------------------
    # Golden Cross / Death Cross
    # ------------------------------------------------------------------
    out["golden_cross"] = (
        (out["ema_50"] > out["ema_200"])
        &
        (out["ema_50"].shift(1) <= out["ema_200"].shift(1))
    )

    out["death_cross"] = (
        (out["ema_50"] < out["ema_200"])
        &
        (out["ema_50"].shift(1) >= out["ema_200"].shift(1))
    )

    # ------------------------------------------------------------------
    # EMA Trend Alignment
    # ------------------------------------------------------------------
    out["ema_trend_up"] = (
        (out["ema_9"] > out["ema_21"])
        &
        (out["ema_21"] > out["ema_50"])
        &
        (out["ema_50"] > out["ema_200"])
    )

    out["ema_trend_down"] = (
        (out["ema_9"] < out["ema_21"])
        &
        (out["ema_21"] < out["ema_50"])
        &
        (out["ema_50"] < out["ema_200"])
    )

    # ------------------------------------------------------------------
    # ATR-normalised EMA50 slope
    # ------------------------------------------------------------------
    lookback = 5

    out["ema50_slope"] = (
        (
            out["ema_50"]
            - out["ema_50"].shift(lookback)
        )
        /
        (
            lookback
            * out["atr_14"].replace(0, np.nan)
        )
    ).fillna(0)

    out["ema50_distance_pct"] = (
        (
            out["close"]
            - out["ema_50"]
        )
        /
        out["ema_50"].replace(0, np.nan)
        * 100
    ).fillna(0)

    # ------------------------------------------------------------------
    # Candle Direction
    # ------------------------------------------------------------------
    out["bullish"] = out["close"] > out["open"]
    out["bearish"] = out["close"] < out["open"]
    out["doji"] = out["close"] == out["open"]

    # ------------------------------------------------------------------
    # Engulfing Patterns
    # ------------------------------------------------------------------
    prev_open = out["open"].shift(1)
    prev_close = out["close"].shift(1)

    out["bullish_engulfing"] = (
        (prev_close < prev_open)
        &
        (out["close"] > out["open"])
        &
        (out["open"] < prev_close)
        &
        (out["close"] > prev_open)
    )

    out["bearish_engulfing"] = (
        (prev_close > prev_open)
        &
        (out["close"] < out["open"])
        &
        (out["open"] > prev_close)
        &
        (out["close"] < prev_open)
    )

    # ------------------------------------------------------------------
    # Swing High / Swing Low
    # ------------------------------------------------------------------
    out["swing_high"] = (
        out["high"]
        ==
        out["high"].rolling(
            5,
            center=True,
            min_periods=5,
        ).max()
    )

    out["swing_low"] = (
        out["low"]
        ==
        out["low"].rolling(
            5,
            center=True,
            min_periods=5,
        ).min()
    )

    
    # ------------------------------------------------------------------
    # ATR %
    # ------------------------------------------------------------------
    out["atr_pct"] = (
        out["atr_14"]
        /
        out["close"].replace(0, np.nan)
        * 100
    ).fillna(0)

    # ------------------------------------------------------------------
    # Volatility Regime
    # ------------------------------------------------------------------
    out["high_volatility"] = out["atr_pct"] > 1.0
    out["medium_volatility"] = (
        (out["atr_pct"] >= 0.5)
        &
        (out["atr_pct"] <= 1.0)
    )
    out["low_volatility"] = out["atr_pct"] < 0.5

    


    # ------------------------------------------------------------------
    # Indicator Ready
    # ------------------------------------------------------------------
    warmup = max(
        200,  # EMA200
        26,   # MACD
        20,   # Volume MA
        14,   # ATR/ADX/RSI
    )

    out["indicator_ready"] = (
        np.arange(len(out)) >= warmup
)

    return out




# ==============================================================
# EMA
# ==============================================================

def ema(
    series: pd.Series,
    span: int,
    *,
    adjust: bool = False,
) -> pd.Series:
    """
    Exponential Moving Average.

    Parameters
    ----------
    series : pd.Series
    span : int
    adjust : bool

    Returns
    -------
    pd.Series
    """

    if span <= 0:
        raise ValueError("EMA span must be > 0")

    series = pd.to_numeric(series, errors="coerce")

    return (
        series
        .ewm(
            span=span,
            adjust=adjust,
            min_periods=1,
        )
        .mean()
    )


# ==============================================================
# RSI (Wilder)
# ==============================================================

def rsi(
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Wilder Relative Strength Index.
    """

    if period <= 0:
        raise ValueError("RSI period must be > 0")

    close = pd.to_numeric(close, errors="coerce")

    delta = close.diff()

    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    rs = avg_gain.divide(
        avg_loss.replace(0, np.nan)
    )

    rsi_value = 100 - (100 / (1 + rs))

    return (
        rsi_value
        .clip(0, 100)
        .fillna(50)
    )


# ==============================================================
# ATR (Wilder)
# ==============================================================

def atr(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """
    Average True Range.
    """

    if period <= 0:
        raise ValueError("ATR period must be > 0")

    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")

    previous_close = close.shift()

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_value = (
        tr
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
    )

    return atr_value.fillna(high - low)


# ==============================================================
# ATR %
# ==============================================================

def atr_percent(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """
    ATR expressed as a percentage of close.
    """

    atr_value = atr(df, period)

    return (
        atr_value
        .divide(df["close"].replace(0, np.nan))
        .multiply(100)
        .fillna(0)
    )


# ==============================================================
# Session VWAP
# ==============================================================

def session_vwap(
    df: pd.DataFrame,
) -> pd.Series:
    """
    Intraday VWAP.
    Resets automatically each session.
    """

    typical_price = (
        df["high"]
        + df["low"]
        + df["close"]
    ) / 3

    volume = (
        df["volume"]
        .fillna(0)
        .astype(float)
    )

    session = df["timestamp"].dt.normalize()

    cumulative_value = (
        (typical_price * volume)
        .groupby(session)
        .cumsum()
    )

    cumulative_volume = (
        volume
        .groupby(session)
        .cumsum()
        .replace(0, np.nan)
    )

    return (
        cumulative_value
        .divide(cumulative_volume)
        .fillna(df["close"])
    )


# ==============================================================
# Rolling VWAP
# ==============================================================

def rolling_vwap(
    df: pd.DataFrame,
    window: int = 20,
) -> pd.Series:
    """
    Rolling VWAP.
    """

    typical_price = (
        df["high"]
        + df["low"]
        + df["close"]
    ) / 3

    value = typical_price * df["volume"]

    return (
        value.rolling(window).sum()
        /
        df["volume"].rolling(window).sum()
    )
def adx(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.DataFrame:
    """
    Calculate Wilder's Average Directional Index (ADX).

    Returns
    -------
    DataFrame
        Columns:
            plus_di
            minus_di
            dx
            adx
    """

    required = {"high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"ADX requires columns: {sorted(missing)}")

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    # ------------------------------------------------------------
    # Directional Movement
    # ------------------------------------------------------------

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where(
        (up_move > down_move) & (up_move > 0),
        0.0,
    )

    minus_dm = down_move.where(
        (down_move > up_move) & (down_move > 0),
        0.0,
    )

    # ------------------------------------------------------------
    # True Range
    # ------------------------------------------------------------

    previous_close = close.shift()

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # ------------------------------------------------------------
    # Wilder ATR
    # ------------------------------------------------------------

    atr_value = (
        true_range
        .ewm(alpha=1 / period, adjust=False)
        .mean()
    )

    atr_value = atr_value.replace(0.0, np.nan)

    # ------------------------------------------------------------
    # Directional Indicators
    # ------------------------------------------------------------

    plus_di = (
        100
        * plus_dm.ewm(alpha=1 / period, adjust=False).mean()
        / atr_value
    )

    minus_di = (
        100
        * minus_dm.ewm(alpha=1 / period, adjust=False).mean()
        / atr_value
    )

    # ------------------------------------------------------------
    # DX
    # ------------------------------------------------------------

    denominator = (plus_di + minus_di).replace(0.0, np.nan)

    dx = (
        100
        * (plus_di - minus_di).abs()
        / denominator
    )

    # ------------------------------------------------------------
    # ADX
    # ------------------------------------------------------------

    adx_value = (
        dx
        .ewm(alpha=1 / period, adjust=False)
        .mean()
    ).fillna(0)

    return pd.DataFrame(
        {
            "plus_di": plus_di.fillna(0),
            "minus_di": minus_di.fillna(0),
            "dx": dx.fillna(0),
            "adx": adx_value,
        },
        index=df.index,
    )


class IndicatorService:
    def prepare(self, data: Any) -> pd.DataFrame:
        return add_core_indicators(prepare_ohlcv(data))

    # ---------------------------------------------------------
    # Moving Averages
    # ---------------------------------------------------------
    def ema(self, series: pd.Series, span: int) -> pd.Series:
        return ema(series, span)

    # ---------------------------------------------------------
    # RSI
    # ---------------------------------------------------------
    def rsi(
        self,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        return rsi(close, period)

    # ---------------------------------------------------------
    # ATR
    # ---------------------------------------------------------
    def atr(
        self,
        df: pd.DataFrame,
        period: int = 14,
    ) -> pd.Series:
        return atr(df, period)

    # ---------------------------------------------------------
    # ADX
    # ---------------------------------------------------------
    def adx(
        self,
        df: pd.DataFrame,
        period: int = 14,
    ) -> pd.Series:
        return adx(df, period)

    # ---------------------------------------------------------
    # Standard MACD (12,26,9)
    # ---------------------------------------------------------
    def macd(
        self,
        close: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> pd.DataFrame:

        ema_fast = ema(close, fast)
        ema_slow = ema(close, slow)

        macd_line = ema_fast - ema_slow
        signal_line = ema(macd_line, signal)
        histogram = macd_line - signal_line

        return pd.DataFrame(
            {
                "macd": macd_line,
                "macd_signal": signal_line,
                "macd_hist": histogram,
            },
            index=close.index,
        )

    # ---------------------------------------------------------
    # VWAP
    # ---------------------------------------------------------
    def vwap(
        self,
        df: pd.DataFrame,
    ) -> pd.Series:
        return session_vwap(df)
#    1. SMA
def sma(series: pd.Series, period: int = 20) -> pd.Series:
    return series.rolling(period, min_periods=1).mean()
# 2. WMA
def wma(series: pd.Series, period: int = 20) -> pd.Series:
    weights = np.arange(1, period + 1)

    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(),
        raw=True,
    )
# 3. ROC
def roc(series: pd.Series, period: int = 12) -> pd.Series:
    return series.pct_change(period) * 100
# 4. Bollinger Bands
def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:

    mid = sma(series, period)
    sigma = series.rolling(period).std()

    return pd.DataFrame(
        {
            "bb_upper": mid + std * sigma,
            "bb_middle": mid,
            "bb_lower": mid - std * sigma,
        }
    )
# 5. Donchian Channel
def donchian_channels(
    df: pd.DataFrame,
    period: int = 20,
) -> pd.DataFrame:

    return pd.DataFrame(
        {
            "donchian_high": df["high"].rolling(period).max(),
            "donchian_low": df["low"].rolling(period).min(),
        }
    )
# 6. OBV
def obv(df: pd.DataFrame) -> pd.Series:

    direction = np.sign(df["close"].diff()).fillna(0)

    return (direction * df["volume"]).cumsum()
# 7. CCI
def cci(
    df: pd.DataFrame,
    period: int = 20,
) -> pd.Series:

    tp = (
        df["high"] +
        df["low"] +
        df["close"]
    ) / 3

    sma_tp = tp.rolling(period).mean()

    mad = tp.rolling(period).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))),
        raw=True,
    )

    return (tp - sma_tp) / (0.015 * mad)
# 8. Heikin Ashi
def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:

    ha = pd.DataFrame(index=df.index)

    ha["ha_close"] = (
        df["open"] +
        df["high"] +
        df["low"] +
        df["close"]
    ) / 4

    ha["ha_open"] = 0.0
    ha.iloc[0, ha.columns.get_loc("ha_open")] = (
        df["open"].iloc[0] +
        df["close"].iloc[0]
    ) / 2

    for i in range(1, len(df)):
        ha.iloc[i, ha.columns.get_loc("ha_open")] = (
            ha["ha_open"].iloc[i - 1]
            + ha["ha_close"].iloc[i - 1]
        ) / 2

    ha["ha_high"] = pd.concat(
        [df["high"], ha["ha_open"], ha["ha_close"]],
        axis=1,
    ).max(axis=1)

    ha["ha_low"] = pd.concat(
        [df["low"], ha["ha_open"], ha["ha_close"]],
        axis=1,
    ).min(axis=1)

    return ha 