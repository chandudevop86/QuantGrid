from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import prepare_ohlcv


@dataclass(frozen=True, slots=True)
class VolumeAnalysisResult:
    symbol: str
    timeframe: str
    current_volume: float
    average_volume_20: float
    average_volume_50: float
    volume_ratio: float
    relative_volume: float
    volume_trend: str
    delivery_percentage: float | None
    volume_spike: bool
    breakout_confirmation: bool
    breakdown_confirmation: bool
    accumulation: bool
    distribution: bool
    institutional_buying: bool
    institutional_selling: bool
    obv: float
    vwap: float
    cmf: float
    ad_line: float
    volume_profile: dict[str, Any]
    smart_money_score: int
    volume_confidence: int
    signal: str
    reason: str
    ai_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_volume(
    *,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    delivery_data: list[dict[str, Any]] | None = None,
) -> VolumeAnalysisResult:
    frame = prepare_ohlcv(candles)
    if frame.empty or len(frame) < 5:
        return _empty_result(symbol, timeframe, "Need at least 5 OHLCV candles for volume analysis.")

    frame = frame.copy()
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    frame["typical_price"] = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    frame["money_flow_volume"] = frame["typical_price"] * frame["volume"]
    frame["vwap"] = _session_vwap(frame)
    frame["obv"] = _obv(frame)
    frame["ad_line"] = _ad_line(frame)
    frame["cmf"] = _cmf(frame, 21)

    latest = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else latest
    prior_high = float(frame["high"].iloc[:-1].tail(20).max()) if len(frame) > 1 else float(latest["high"])
    prior_low = float(frame["low"].iloc[:-1].tail(20).min()) if len(frame) > 1 else float(latest["low"])

    current_volume = float(latest["volume"])
    avg20 = float(frame["volume"].tail(20).mean())
    avg50 = float(frame["volume"].tail(50).mean())
    baseline = avg20 or avg50 or current_volume or 1.0
    relative_volume = current_volume / baseline if baseline > 0 else 0.0
    volume_ratio = current_volume / avg50 if avg50 > 0 else relative_volume
    volume_trend = _volume_trend(frame["volume"])
    delivery_percentage = _delivery_percentage(delivery_data)

    close = float(latest["close"])
    open_price = float(latest["open"])
    previous_close = float(previous["close"])
    vwap = float(latest["vwap"])
    cmf = float(latest["cmf"])
    obv_now = float(latest["obv"])
    obv_prior = float(frame["obv"].iloc[-5]) if len(frame) >= 5 else float(frame["obv"].iloc[0])
    ad_now = float(latest["ad_line"])
    ad_prior = float(frame["ad_line"].iloc[-5]) if len(frame) >= 5 else float(frame["ad_line"].iloc[0])

    volume_spike = bool(relative_volume >= 1.5)
    breakout_confirmation = bool(close > prior_high and volume_spike and close >= open_price)
    breakdown_confirmation = bool(close < prior_low and volume_spike and close <= open_price)
    accumulation = bool(close >= previous_close and cmf > 0.05 and ad_now >= ad_prior and obv_now >= obv_prior)
    distribution = bool(close <= previous_close and cmf < -0.05 and ad_now <= ad_prior and obv_now <= obv_prior)
    institutional_buying = bool(relative_volume >= 1.2 and close > vwap and accumulation)
    institutional_selling = bool(relative_volume >= 1.2 and close < vwap and distribution)

    profile = volume_profile(frame)
    smart_money_score = _smart_money_score(
        relative_volume=relative_volume,
        cmf=cmf,
        close=close,
        vwap=vwap,
        obv_rising=obv_now >= obv_prior,
        ad_rising=ad_now >= ad_prior,
        delivery_percentage=delivery_percentage,
        breakout_confirmation=breakout_confirmation,
        breakdown_confirmation=breakdown_confirmation,
    )
    volume_confidence = _volume_confidence(
        relative_volume=relative_volume,
        volume_trend=volume_trend,
        current_volume=current_volume,
        cmf=cmf,
        smart_money_score=smart_money_score,
    )
    signal = _signal(
        breakout_confirmation=breakout_confirmation,
        breakdown_confirmation=breakdown_confirmation,
        institutional_buying=institutional_buying,
        institutional_selling=institutional_selling,
        confidence=volume_confidence,
        smart_money_score=smart_money_score,
    )
    reason = _reason(signal, relative_volume, volume_trend, cmf, close, vwap)
    return VolumeAnalysisResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        current_volume=round(current_volume, 2),
        average_volume_20=round(avg20, 2),
        average_volume_50=round(avg50, 2),
        volume_ratio=round(volume_ratio, 3),
        relative_volume=round(relative_volume, 3),
        volume_trend=volume_trend,
        delivery_percentage=round(delivery_percentage, 2) if delivery_percentage is not None else None,
        volume_spike=volume_spike,
        breakout_confirmation=breakout_confirmation,
        breakdown_confirmation=breakdown_confirmation,
        accumulation=accumulation,
        distribution=distribution,
        institutional_buying=institutional_buying,
        institutional_selling=institutional_selling,
        obv=round(obv_now, 2),
        vwap=round(vwap, 2),
        cmf=round(cmf, 4),
        ad_line=round(ad_now, 2),
        volume_profile=profile,
        smart_money_score=smart_money_score,
        volume_confidence=volume_confidence,
        signal=signal,
        reason=reason,
        ai_summary=_summary(signal, reason),
    )


def volume_profile(frame: pd.DataFrame, bins: int = 12) -> dict[str, Any]:
    if frame.empty:
        return {"poc": None, "vah": None, "val": None, "hvn": [], "lvn": []}
    prices = ((frame["high"] + frame["low"] + frame["close"]) / 3.0).astype(float)
    volumes = frame["volume"].fillna(0.0).astype(float)
    low = float(prices.min())
    high = float(prices.max())
    if low == high:
        total_volume = float(volumes.sum())
        return {"poc": round(low, 2), "vah": round(high, 2), "val": round(low, 2), "hvn": [round(low, 2)], "lvn": [], "total_volume": round(total_volume, 2)}

    bucket_count = max(4, min(int(bins), 24))
    bucket_width = (high - low) / bucket_count
    buckets: list[dict[str, float]] = []
    for index in range(bucket_count):
        start = low + index * bucket_width
        end = high if index == bucket_count - 1 else start + bucket_width
        mask = (prices >= start) & (prices <= end if index == bucket_count - 1 else prices < end)
        buckets.append({"price": (start + end) / 2.0, "volume": float(volumes[mask].sum())})

    total_volume = sum(bucket["volume"] for bucket in buckets)
    poc_bucket = max(buckets, key=lambda bucket: bucket["volume"])
    sorted_buckets = sorted(buckets, key=lambda bucket: bucket["volume"], reverse=True)
    value_area: list[dict[str, float]] = []
    running = 0.0
    for bucket in sorted_buckets:
        value_area.append(bucket)
        running += bucket["volume"]
        if total_volume <= 0 or running >= total_volume * 0.7:
            break
    vah = max(bucket["price"] for bucket in value_area)
    val = min(bucket["price"] for bucket in value_area)
    average_bucket_volume = total_volume / max(len(buckets), 1)
    hvn = [round(bucket["price"], 2) for bucket in buckets if bucket["volume"] >= average_bucket_volume * 1.25]
    lvn = [round(bucket["price"], 2) for bucket in buckets if 0 < bucket["volume"] <= average_bucket_volume * 0.5]
    return {
        "poc": round(float(poc_bucket["price"]), 2),
        "vah": round(float(vah), 2),
        "val": round(float(val), 2),
        "hvn": hvn[:5],
        "lvn": lvn[:5],
        "total_volume": round(total_volume, 2),
    }


def _session_vwap(frame: pd.DataFrame) -> pd.Series:
    session = frame["timestamp"].dt.strftime("%Y-%m-%d")
    value = frame["money_flow_volume"].groupby(session).cumsum()
    volume = frame["volume"].groupby(session).cumsum().replace(0.0, pd.NA)
    return value.div(volume).fillna(frame["close"]).astype(float)


def _obv(frame: pd.DataFrame) -> pd.Series:
    direction = frame["close"].diff().fillna(0.0).apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    return (direction * frame["volume"]).cumsum()


def _ad_line(frame: pd.DataFrame) -> pd.Series:
    high_low = (frame["high"] - frame["low"]).replace(0.0, pd.NA)
    money_flow_multiplier = (((frame["close"] - frame["low"]) - (frame["high"] - frame["close"])) / high_low).fillna(0.0)
    return (money_flow_multiplier * frame["volume"]).cumsum()


def _cmf(frame: pd.DataFrame, period: int) -> pd.Series:
    high_low = (frame["high"] - frame["low"]).replace(0.0, pd.NA)
    multiplier = (((frame["close"] - frame["low"]) - (frame["high"] - frame["close"])) / high_low).fillna(0.0)
    money_flow = multiplier * frame["volume"]
    volume_sum = frame["volume"].rolling(period, min_periods=3).sum().replace(0.0, pd.NA)
    return money_flow.rolling(period, min_periods=3).sum().div(volume_sum).fillna(0.0)


def _volume_trend(volume: pd.Series) -> str:
    if len(volume) < 6:
        return "Unknown"
    recent = float(volume.tail(5).mean())
    previous = float(volume.iloc[:-5].tail(5).mean()) if len(volume) >= 10 else float(volume.head(max(len(volume) - 5, 1)).mean())
    if previous <= 0:
        return "Unknown"
    if recent >= previous * 1.15:
        return "Rising"
    if recent <= previous * 0.85:
        return "Falling"
    return "Stable"


def _delivery_percentage(delivery_data: list[dict[str, Any]] | None) -> float | None:
    if not delivery_data:
        return None
    latest = delivery_data[-1]
    for key in ("delivery_percentage", "delivery_percent", "delivery_pct"):
        if latest.get(key) is not None:
            return float(latest[key])
    delivered = latest.get("delivered_quantity")
    traded = latest.get("traded_quantity") or latest.get("volume")
    if delivered is not None and traded:
        return float(delivered) / max(float(traded), 1.0) * 100.0
    return None


def _smart_money_score(
    *,
    relative_volume: float,
    cmf: float,
    close: float,
    vwap: float,
    obv_rising: bool,
    ad_rising: bool,
    delivery_percentage: float | None,
    breakout_confirmation: bool,
    breakdown_confirmation: bool,
) -> int:
    score = 50
    score += 12 if relative_volume >= 1.5 else 6 if relative_volume >= 1.2 else -8 if relative_volume < 0.8 else 0
    score += 10 if close > vwap else -10 if close < vwap else 0
    score += 8 if cmf > 0.05 else -8 if cmf < -0.05 else 0
    score += 6 if obv_rising else -6
    score += 6 if ad_rising else -6
    if delivery_percentage is not None:
        score += 8 if delivery_percentage >= 55 else -6 if delivery_percentage <= 35 else 0
    if breakout_confirmation:
        score += 10
    if breakdown_confirmation:
        score -= 10
    return max(0, min(100, int(score)))


def _volume_confidence(*, relative_volume: float, volume_trend: str, current_volume: float, cmf: float, smart_money_score: int) -> int:
    score = 35
    score += 25 if relative_volume >= 1.5 else 15 if relative_volume >= 1.2 else 5 if relative_volume >= 0.9 else -10
    score += 12 if volume_trend == "Rising" else 4 if volume_trend == "Stable" else -8 if volume_trend == "Falling" else 0
    score += 10 if current_volume > 0 else -20
    score += 8 if abs(cmf) >= 0.05 else 0
    score += int((smart_money_score - 50) * 0.3)
    return max(0, min(100, int(score)))


def _signal(
    *,
    breakout_confirmation: bool,
    breakdown_confirmation: bool,
    institutional_buying: bool,
    institutional_selling: bool,
    confidence: int,
    smart_money_score: int,
) -> str:
    if confidence < 45:
        return "NO TRADE"
    if breakout_confirmation or (institutional_buying and smart_money_score >= 62):
        return "BUY"
    if breakdown_confirmation or (institutional_selling and smart_money_score <= 38):
        return "SELL"
    if confidence >= 55:
        return "WAIT"
    return "NO TRADE"


def _reason(signal: str, relative_volume: float, volume_trend: str, cmf: float, close: float, vwap: float) -> str:
    location = "above VWAP" if close > vwap else "below VWAP" if close < vwap else "at VWAP"
    flow = "positive money flow" if cmf > 0.05 else "negative money flow" if cmf < -0.05 else "neutral money flow"
    return f"{signal}: relative volume is {relative_volume:.2f}x, volume trend is {volume_trend.lower()}, price is {location}, and CMF shows {flow}."


def _summary(signal: str, reason: str) -> str:
    if signal == "BUY":
        return f"Volume supports bullish participation. {reason}"
    if signal == "SELL":
        return f"Volume supports bearish participation. {reason}"
    if signal == "WAIT":
        return f"Volume is informative but not decisive. {reason}"
    return f"Volume does not justify a trade. {reason}"


def _empty_result(symbol: str, timeframe: str, reason: str) -> VolumeAnalysisResult:
    return VolumeAnalysisResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        current_volume=0.0,
        average_volume_20=0.0,
        average_volume_50=0.0,
        volume_ratio=0.0,
        relative_volume=0.0,
        volume_trend="Unknown",
        delivery_percentage=None,
        volume_spike=False,
        breakout_confirmation=False,
        breakdown_confirmation=False,
        accumulation=False,
        distribution=False,
        institutional_buying=False,
        institutional_selling=False,
        obv=0.0,
        vwap=0.0,
        cmf=0.0,
        ad_line=0.0,
        volume_profile={"poc": None, "vah": None, "val": None, "hvn": [], "lvn": []},
        smart_money_score=0,
        volume_confidence=0,
        signal="NO TRADE",
        reason=reason,
        ai_summary=f"Volume analysis unavailable. {reason}",
    )
