from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.signal import StrategySignal


def _round(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _last_swing_high(frame: pd.DataFrame, lookback: int = 20) -> float:
    window = frame.tail(lookback)
    return _round(window["high"].max())


def _last_swing_low(frame: pd.DataFrame, lookback: int = 20) -> float:
    window = frame.tail(lookback)
    return _round(window["low"].min())


def _trend(row: pd.Series) -> tuple[str, str]:
    ema9, ema21, ema50, ema200 = (float(row[key]) for key in ("ema_9", "ema_21", "ema_50", "ema_200"))
    close = float(row["close"])
    if close > float(row["vwap"]) and ema9 > ema21 > ema50 > ema200:
        return "bullish", "Price is above VWAP with stacked bullish EMAs."
    if close < float(row["vwap"]) and ema9 < ema21 < ema50 < ema200:
        return "bearish", "Price is below VWAP with stacked bearish EMAs."
    return "range", "EMA/VWAP alignment is mixed, so trend quality is not institutional-grade."


def _structure(frame: pd.DataFrame) -> tuple[str, list[str]]:
    recent = frame.tail(8)
    previous = frame.iloc[-20:-8] if len(frame) >= 20 else frame.head(max(len(frame) - 8, 1))
    current_high = float(recent["high"].max())
    current_low = float(recent["low"].min())
    previous_high = float(previous["high"].max())
    previous_low = float(previous["low"].min())
    reasons: list[str] = []

    if current_high > previous_high and current_low > previous_low:
        reasons.append("Recent price made a higher high and protected a higher low.")
        return "bullish BOS", reasons
    if current_low < previous_low and current_high < previous_high:
        reasons.append("Recent price made a lower low and rejected below prior structure.")
        return "bearish BOS", reasons
    if current_high > previous_high and current_low < previous_low:
        reasons.append("Both sides of the range were swept; trap/range behavior is elevated.")
        return "two-sided liquidity sweep / chop", reasons

    reasons.append("No clean break of structure; price is rotating inside recent range.")
    return "range / no confirmed BOS", reasons


def _liquidity(frame: pd.DataFrame, row: pd.Series, support: float, resistance: float) -> tuple[str, list[str]]:
    close = float(row["close"])
    atr = max(float(row.get("atr_14", 0.0) or 0.0), 0.01)
    distance_to_high = abs(resistance - close)
    distance_to_low = abs(close - support)
    reasons: list[str] = []

    if distance_to_high <= atr:
        reasons.append("Price is trading near buy-side liquidity above recent highs.")
    if distance_to_low <= atr:
        reasons.append("Price is trading near sell-side liquidity below recent lows.")

    previous = frame.iloc[-2] if len(frame) > 1 else row
    if float(row["high"]) > resistance and close < resistance:
        reasons.append("Potential buy-side stop hunt: high swept resistance but closed back below.")
    if float(row["low"]) < support and close > support:
        reasons.append("Potential sell-side stop hunt: low swept support but closed back above.")

    if float(row["bar_range"]) > float(previous.get("bar_range", row["bar_range"])) * 1.8:
        reasons.append("Current candle range expanded sharply; move may be event-driven or aggressive institutional repricing.")

    if not reasons:
        reasons.append("No fresh liquidity sweep; liquidity remains resting around range extremes.")
    return " ".join(reasons), reasons


def _volume_behavior(row: pd.Series) -> str:
    volume = row.get("volume")
    if pd.isna(volume) or volume is None:
        return "Volume unavailable for index feed; using range expansion as proxy."
    return "Volume is present but no relative-volume baseline is implemented yet."


def _levels(frame: pd.DataFrame) -> dict[str, Any]:
    session = frame.tail(75)
    support = _last_swing_low(session)
    resistance = _last_swing_high(session)
    close = float(frame.iloc[-1]["close"])
    atr = max(float(frame.iloc[-1].get("atr_14", 0.0) or 0.0), 1.0)

    return {
        "intraday_support": support,
        "intraday_resistance": resistance,
        "demand_zone": [_round(support), _round(support + atr * 0.45)],
        "supply_zone": [_round(resistance - atr * 0.45), _round(resistance)],
        "breakout_levels": {"above": resistance, "below": support},
        "liquidity_pools": {
            "buy_side": _round(resistance + atr * 0.15),
            "sell_side": _round(support - atr * 0.15),
        },
        "vwap": _round(frame.iloc[-1]["vwap"]),
        "last_price": _round(close),
    }


def _best_signal(signals: list[StrategySignal]) -> StrategySignal | None:
    if not signals:
        return None

    def rank(signal: StrategySignal) -> float:
        return float(signal.metadata.get("total_score") or signal.metadata.get("score") or 0.0)

    return max(signals, key=rank)


def analyze_market_structure(
    candles: list[dict[str, Any]],
    *,
    signals: list[StrategySignal] | None = None,
    raw_signals: list[StrategySignal] | None = None,
) -> dict[str, Any]:
    signals = signals or []
    raw_signals = raw_signals or []
    if len(candles) < 20:
        return {
            "bias": "range",
            "market_structure": "insufficient candles",
            "entry": 0,
            "stop_loss": 0,
            "targets": [0, 0, 0],
            "risk_reward": "",
            "setup_type": "wait",
            "confidence_score": 0,
            "liquidity_analysis": "Need at least 20 candles for institutional structure analysis.",
            "levels": {},
            "institutional_activity_probability": "low",
            "trade_decision": "WAIT",
            "reasoning": ["Insufficient candles for BOS/CHoCH/liquidity analysis."],
        }

    frame = IndicatorService().prepare(candles)
    row = frame.iloc[-1]
    bias, trend_reason = _trend(row)
    market_structure, structure_reasons = _structure(frame)
    levels = _levels(frame)
    liquidity_text, liquidity_reasons = _liquidity(frame, row, levels["intraday_support"], levels["intraday_resistance"])
    volume_reason = _volume_behavior(row)
    selected = _best_signal(signals)

    reasoning = [trend_reason, *structure_reasons, *liquidity_reasons, volume_reason]
    if not selected:
        raw_note = f"{len(raw_signals)} raw setup(s) found but none passed live/high-quality validation." if raw_signals else "No raw strategy setup is present on the latest candles."
        reasoning.append(raw_note)
        reasoning.append("No trade: wait for BOS plus retest with VWAP/EMA/momentum confluence.")
        return {
            "bias": bias,
            "market_structure": market_structure,
            "entry": 0,
            "stop_loss": 0,
            "targets": [0, 0, 0],
            "risk_reward": "",
            "setup_type": "no_trade",
            "confidence_score": 0,
            "liquidity_analysis": liquidity_text,
            "levels": levels,
            "institutional_activity_probability": "medium" if "sweep" in liquidity_text.lower() else "low",
            "trade_decision": "WAIT",
            "weak_signal_detected": bool(raw_signals),
            "news_driven_or_organic": "possible news/impulse" if "expanded sharply" in liquidity_text else "organic or normal auction",
            "reasoning": reasoning,
        }

    risk = abs(float(selected.entry_price) - float(selected.stop_loss))
    reward = abs(float(selected.target_price) - float(selected.entry_price))
    rr = reward / risk if risk > 0 else 0.0
    score = min(10, max(1, int(round(float(selected.metadata.get("total_score") or selected.metadata.get("score") or 5)))))
    side_bias_conflict = (selected.side == "BUY" and bias == "bearish") or (selected.side == "SELL" and bias == "bullish")
    if side_bias_conflict:
        reasoning.append("Signal direction conflicts with EMA/VWAP bias; treat as countertrend unless liquidity sweep is explicit.")

    return {
        "bias": bias,
        "market_structure": market_structure,
        "entry": _round(selected.entry_price),
        "stop_loss": _round(selected.stop_loss),
        "targets": [
            _round(selected.entry_price + (reward * 0.5 if selected.side == "BUY" else -reward * 0.5)),
            _round(selected.target_price),
            _round(selected.entry_price + (reward * 1.5 if selected.side == "BUY" else -reward * 1.5)),
        ],
        "risk_reward": f"1:{rr:.2f}",
        "setup_type": str(selected.metadata.get("market_signal") or selected.metadata.get("setup") or selected.strategy_name),
        "confidence_score": score,
        "liquidity_analysis": liquidity_text,
        "levels": levels,
        "institutional_activity_probability": "high" if score >= 8 and "sweep" in liquidity_text.lower() else "medium",
        "trade_decision": "TRADE" if score >= 7 and not side_bias_conflict else "WAIT",
        "weak_signal_detected": score < 7 or side_bias_conflict,
        "news_driven_or_organic": "possible news/impulse" if "expanded sharply" in liquidity_text else "organic or normal auction",
        "reasoning": reasoning,
    }
