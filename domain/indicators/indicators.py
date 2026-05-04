from __future__ import annotations

from typing import Any

import pandas as pd


OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def prepare_ohlcv(data: Any) -> pd.DataFrame:
    df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    df.columns = [str(column).strip().lower() for column in df.columns]
    rename_map = {"datetime": "timestamp", "date": "timestamp", "time": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "vol": "volume"}
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

    return df.dropna(subset=["timestamp", "open", "high", "low", "close"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def add_core_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["bar_range"] = (out["high"] - out["low"]).clip(lower=0.0)
    out["body_size"] = (out["close"] - out["open"]).abs()
    out["ema_9"] = ema(out["close"], 9)
    out["ema_21"] = ema(out["close"], 21)
    out["ema_50"] = ema(out["close"], 50)
    out["ema_200"] = ema(out["close"], 200)
    out["ema_fast"] = out["ema_9"]
    out["ema_slow"] = out["ema_21"]
    out["macd"] = out["ema_9"] - out["ema_21"]
    out["macd_signal"] = ema(out["macd"], 9)
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    out["rsi"] = rsi(out["close"], 14)
    out["session_day"] = out["timestamp"].dt.strftime("%Y-%m-%d")
    out["vwap"] = session_vwap(out)
    out["avg_range_5"] = out["bar_range"].rolling(5, min_periods=1).mean()
    out["recent_high"] = out["high"].shift(1).rolling(6, min_periods=2).max()
    out["recent_low"] = out["low"].shift(1).rolling(6, min_periods=2).min()
    out["bullish_fvg_gap"] = (out["low"] - out["high"].shift(2)).clip(lower=0.0)
    out["bearish_fvg_gap"] = (out["low"].shift(2) - out["high"]).clip(lower=0.0)
    return out


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=int(span), adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff().fillna(0.0)
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / int(period), adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / int(period), adjust=False).mean().replace(0.0, float("nan"))
    rs = avg_gain.div(avg_loss)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = df["volume"].fillna(0.0)
    session_value = (typical_price * volume).groupby(df["session_day"]).cumsum()
    session_volume = volume.groupby(df["session_day"]).cumsum().replace(0.0, pd.NA)
    return session_value.div(session_volume).fillna(df["close"]).astype(float)


class IndicatorService:
    def prepare(self, data: Any) -> pd.DataFrame:
        return add_core_indicators(prepare_ohlcv(data))

    def ema(self, series: pd.Series, span: int) -> pd.Series:
        return ema(series, span)

    def rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        return rsi(close, period)

    def macd(self, close: pd.Series, fast: int = 9, slow: int = 21, signal: int = 9) -> pd.DataFrame:
        macd_line = ema(close, fast) - ema(close, slow)
        signal_line = ema(macd_line, signal)
        return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": macd_line - signal_line})

    def vwap(self, df: pd.DataFrame) -> pd.Series:
        return session_vwap(df)
