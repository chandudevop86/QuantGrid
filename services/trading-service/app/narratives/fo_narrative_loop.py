from __future__ import annotations

from datetime import datetime, time, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


IST = ZoneInfo("Asia/Kolkata")


class MarketRegime(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    SIDEWAYS = "Sideways"
    VOLATILE = "Volatile"
    EXPIRY_TRAP = "Expiry trap"


class OptionBias(str, Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    NO_TRADE = "NO_TRADE"


class RiskPlan(BaseModel):
    entry: str
    stop_loss: str
    targets: list[str] = Field(default_factory=list)
    risk_reward: str = "Only valid after confirmation."


class NarrativeInput(BaseModel):
    symbol: str = "NIFTY"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    spot_price: float
    futures_price: float | None = None
    option_chain: list[dict[str, Any]] = Field(default_factory=list)
    option_chain_quality: dict[str, Any] | None = None
    pcr: float | None = None
    india_vix: float | None = None
    india_vix_change_pct: float | None = None
    fii_cash: float | None = None
    dii_cash: float | None = None
    fii_index_futures: float | None = None
    max_pain: float | None = None
    gift_nifty_change_pct: float | None = None
    usdinr_change_pct: float | None = None
    brent_change_pct: float | None = None
    global_market_cues: float | None = None
    previous_spot: float | None = None
    is_expiry_day: bool = False
    days_to_expiry: int | None = None


class NarrativeSignal(BaseModel):
    signal: OptionBias
    confidence: int
    market_regime: MarketRegime
    reason: str
    why_now: str
    invalidation: str
    key_levels: dict[str, float | None]
    option_strike_suggestion: str
    risk_plan: RiskPlan
    expiry_warning: str
    detected_patterns: list[str] = Field(default_factory=list)
    explanation: str
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)


class _ChainSummary(BaseModel):
    support: float | None = None
    resistance: float | None = None
    highest_call_oi: float | None = None
    highest_put_oi: float | None = None
    call_oi_change: float = 0.0
    put_oi_change: float = 0.0
    call_volume: float = 0.0
    put_volume: float = 0.0
    total_call_oi: float = 0.0
    total_put_oi: float = 0.0


def is_market_hours_ist(now: datetime | None = None) -> bool:
    current = (now or datetime.now(timezone.utc)).astimezone(IST)
    if current.weekday() >= 5:
        return False
    return time(9, 15) <= current.time() <= time(15, 30)


def generate_narrative_signal(payload: NarrativeInput) -> NarrativeSignal:
    summary = _summarize_chain(payload)
    pcr = _coalesce(payload.pcr, _safe_ratio(summary.total_put_oi, summary.total_call_oi), 1.0)
    futures_premium = _futures_premium_pct(payload)
    support = summary.support
    resistance = summary.resistance
    max_pain = _coalesce(payload.max_pain, summary.support, summary.resistance, payload.spot_price)
    patterns = _detect_patterns(payload, summary, pcr, futures_premium)
    regime = _market_regime(payload, patterns, pcr, support, resistance, max_pain)
    between_levels = support is not None and resistance is not None and support <= payload.spot_price <= resistance

    ce_confirmations = _ce_confirmations(payload, patterns, futures_premium)
    pe_confirmations = _pe_confirmations(payload, patterns, futures_premium)
    signal = OptionBias.NO_TRADE
    reason = "Price is inside the option-chain support/resistance band; confirmation is incomplete."
    why_now = "Wait for price to leave the range with OI and futures confirmation."
    invalidation = "A confirmed breakout or breakdown changes the setup."

    if (
        not between_levels
        and "Resistance breakout" in patterns
        and "Fake breakout" not in patterns
        and ce_confirmations >= 2
        and regime != MarketRegime.EXPIRY_TRAP
    ):
        signal = OptionBias.BUY_CE
        reason = "Resistance breakout has confirmation from derivatives positioning."
        why_now = "Spot is above call-side resistance while put support or futures/global cues confirm upside follow-through."
        invalidation = f"Trade invalidates if spot falls back below {resistance or payload.spot_price:.2f}."
    elif (
        not between_levels
        and "Support breakdown" in patterns
        and "Fake breakdown" not in patterns
        and pe_confirmations >= 2
        and regime != MarketRegime.EXPIRY_TRAP
    ):
        signal = OptionBias.BUY_PE
        reason = "Support breakdown has confirmation from derivatives positioning."
        why_now = "Spot is below put-side support while call writing or weak futures/global cues confirm downside pressure."
        invalidation = f"Trade invalidates if spot recovers above {support or payload.spot_price:.2f}."
    elif "Fake breakout" in patterns or "Fake breakdown" in patterns:
        reason = "Breakout attempt lacks clean confirmation and volatility/PCR conditions are hostile."
        why_now = "False-break risk is elevated right now; avoid chasing premium."
        invalidation = "A fresh close beyond the level with OI confirmation and cooling VIX invalidates the no-trade view."
    elif regime == MarketRegime.EXPIRY_TRAP:
        reason = "Expiry/max-pain conditions favor whipsaw and premium crush."
        why_now = "Price is close to max pain or PCR is stretched near expiry, so directional reward is poor."
        invalidation = "A decisive range break with fresh OI confirmation invalidates the trap view."

    confidence = _confidence(signal, payload, patterns, pcr, ce_confirmations, pe_confirmations, between_levels, regime)
    risk_plan = _risk_plan(signal, payload, support, resistance)
    expiry_warning = _expiry_warning(payload, regime)
    explanation = (
        f"{signal.value}: {reason} Why now: {why_now} "
        f"Invalidation: {invalidation} Regime: {regime.value}."
    )

    return NarrativeSignal(
        signal=signal,
        confidence=confidence,
        market_regime=regime,
        reason=reason,
        why_now=why_now,
        invalidation=invalidation,
        key_levels={
            "support": support,
            "resistance": resistance,
            "invalidation": _invalidation_level(signal, payload, support, resistance),
            "max_pain": float(max_pain) if max_pain is not None else None,
        },
        option_strike_suggestion=_option_strike_suggestion(signal, payload),
        risk_plan=risk_plan,
        expiry_warning=expiry_warning,
        detected_patterns=patterns,
        explanation=explanation,
        inputs_snapshot={
            "spot_price": payload.spot_price,
            "futures_price": payload.futures_price,
            "pcr": round(pcr, 3),
            "india_vix": payload.india_vix,
            "india_vix_change_pct": payload.india_vix_change_pct,
            "futures_premium_pct": round(futures_premium, 3),
            "fii_cash": payload.fii_cash,
            "dii_cash": payload.dii_cash,
            "fii_index_futures": payload.fii_index_futures,
            "gift_nifty_change_pct": payload.gift_nifty_change_pct,
            "global_market_cues": payload.global_market_cues,
            "option_chain_quality": payload.option_chain_quality,
        },
    )


def _summarize_chain(payload: NarrativeInput) -> _ChainSummary:
    rows = list(payload.option_chain or [])
    if not rows:
        spot = payload.spot_price
        return _ChainSummary(support=spot * 0.995, resistance=spot * 1.005)

    total_call_oi = total_put_oi = call_change = put_change = call_volume = put_volume = 0.0
    highest_call = highest_put = None
    highest_call_oi = highest_put_oi = -1.0
    support_candidates: list[tuple[float, float]] = []
    resistance_candidates: list[tuple[float, float]] = []
    for row in rows:
        strike = _optional_number(row.get("strike"))
        ce = row.get("ce") or row.get("CE") or {}
        pe = row.get("pe") or row.get("PE") or {}
        call_oi = _number(ce.get("oi") or ce.get("openInterest") or ce.get("open_interest"))
        put_oi = _number(pe.get("oi") or pe.get("openInterest") or pe.get("open_interest"))
        ce_change = _number(ce.get("oi_change") or ce.get("change_oi") or ce.get("changeinOpenInterest") or ce.get("oiChange"))
        pe_change = _number(pe.get("oi_change") or pe.get("change_oi") or pe.get("changeinOpenInterest") or pe.get("oiChange"))
        total_call_oi += call_oi
        total_put_oi += put_oi
        call_change += ce_change
        put_change += pe_change
        call_volume += _number(ce.get("volume"))
        put_volume += _number(pe.get("volume"))
        if strike is None:
            continue
        if call_oi > highest_call_oi:
            highest_call_oi, highest_call = call_oi, strike
        if put_oi > highest_put_oi:
            highest_put_oi, highest_put = put_oi, strike
        if strike <= payload.spot_price:
            support_candidates.append((strike, put_oi))
        if strike >= payload.spot_price:
            resistance_candidates.append((strike, call_oi))

    return _ChainSummary(
        support=max(support_candidates, key=lambda item: item[1])[0] if support_candidates else highest_put,
        resistance=max(resistance_candidates, key=lambda item: item[1])[0] if resistance_candidates else highest_call,
        highest_call_oi=highest_call,
        highest_put_oi=highest_put,
        call_oi_change=call_change,
        put_oi_change=put_change,
        call_volume=call_volume,
        put_volume=put_volume,
        total_call_oi=total_call_oi,
        total_put_oi=total_put_oi,
    )


def _detect_patterns(payload: NarrativeInput, summary: _ChainSummary, pcr: float, futures_premium: float) -> list[str]:
    patterns: list[str] = []
    if summary.call_oi_change > max(summary.put_oi_change, 1.0) * 1.15 and summary.call_oi_change > 0:
        patterns.append("Call writing")
    if summary.put_oi_change > max(summary.call_oi_change, 1.0) * 1.15 and summary.put_oi_change > 0:
        patterns.append("Put writing")
    if summary.call_oi_change < 0 and payload.spot_price > _coalesce(summary.resistance, payload.spot_price):
        patterns.append("Short covering")
    if futures_premium > 0.08 and payload.previous_spot and payload.spot_price > payload.previous_spot:
        patterns.append("Long buildup")
    if futures_premium < -0.08 and payload.previous_spot and payload.spot_price < payload.previous_spot:
        patterns.append("Long unwinding")
    if summary.support is not None and payload.spot_price < summary.support:
        patterns.append("Support breakdown")
    if summary.resistance is not None and payload.spot_price > summary.resistance:
        patterns.append("Resistance breakout")
    if "Resistance breakout" in patterns and (summary.put_oi_change <= 0 or _vix_rising(payload) or pcr > 1.4):
        patterns.append("Fake breakout")
    if "Support breakdown" in patterns and (summary.call_oi_change <= 0 or _vix_rising(payload) or pcr < 0.8):
        patterns.append("Fake breakdown")
    if abs(summary.call_oi_change + summary.put_oi_change) > 0 and _vix_rising(payload) and (pcr < 0.8 or pcr > 1.4):
        patterns.append("Stop-loss cascade")
    if payload.previous_spot and abs(payload.spot_price - payload.previous_spot) / max(payload.previous_spot, 1.0) < 0.001 and (pcr < 0.85 or pcr > 1.3):
        patterns.append("Reversal attempt")
    return patterns


def _market_regime(
    payload: NarrativeInput,
    patterns: list[str],
    pcr: float,
    support: float | None,
    resistance: float | None,
    max_pain: float | None,
) -> MarketRegime:
    near_expiry = payload.is_expiry_day or (payload.days_to_expiry is not None and payload.days_to_expiry <= 0)
    near_max_pain = max_pain is not None and abs(payload.spot_price - float(max_pain)) / max(payload.spot_price, 1.0) <= 0.003
    if near_expiry and (near_max_pain or pcr < 0.8 or pcr > 1.35):
        return MarketRegime.EXPIRY_TRAP
    if _vix_rising(payload) or _coalesce(payload.india_vix, 0.0) >= 18.0:
        return MarketRegime.VOLATILE
    if support is not None and resistance is not None and support <= payload.spot_price <= resistance:
        return MarketRegime.SIDEWAYS
    if "Resistance breakout" in patterns and "Fake breakout" not in patterns:
        return MarketRegime.BULLISH
    if "Support breakdown" in patterns and "Fake breakdown" not in patterns:
        return MarketRegime.BEARISH
    return MarketRegime.SIDEWAYS


def _ce_confirmations(payload: NarrativeInput, patterns: list[str], futures_premium: float) -> int:
    checks = [
        "Resistance breakout" in patterns,
        "Put writing" in patterns or "Short covering" in patterns,
        futures_premium > 0,
        _coalesce(payload.fii_cash, 0.0) > 0 or _coalesce(payload.fii_index_futures, 0.0) > 0,
        _coalesce(payload.gift_nifty_change_pct, 0.0) > 0 or _coalesce(payload.global_market_cues, 0.0) > 0,
    ]
    return sum(1 for item in checks if item)


def _pe_confirmations(payload: NarrativeInput, patterns: list[str], futures_premium: float) -> int:
    checks = [
        "Support breakdown" in patterns,
        "Call writing" in patterns or "Long unwinding" in patterns,
        futures_premium < 0,
        _coalesce(payload.fii_cash, 0.0) < 0 or _coalesce(payload.fii_index_futures, 0.0) < 0,
        _coalesce(payload.gift_nifty_change_pct, 0.0) < 0 or _coalesce(payload.global_market_cues, 0.0) < 0,
    ]
    return sum(1 for item in checks if item)


def _confidence(
    signal: OptionBias,
    payload: NarrativeInput,
    patterns: list[str],
    pcr: float,
    ce_confirmations: int,
    pe_confirmations: int,
    between_levels: bool,
    regime: MarketRegime,
) -> int:
    if signal == OptionBias.NO_TRADE:
        base = 68 if between_levels or regime == MarketRegime.EXPIRY_TRAP else 55
    elif signal == OptionBias.BUY_CE:
        base = 48 + ce_confirmations * 10
    else:
        base = 48 + pe_confirmations * 10
    if _vix_rising(payload) and (pcr < 0.8 or pcr > 1.4):
        base -= 20
    elif _vix_rising(payload):
        base -= 10
    if "Fake breakout" in patterns or "Fake breakdown" in patterns:
        base -= 18
    if payload.is_expiry_day or (payload.days_to_expiry is not None and payload.days_to_expiry <= 0):
        base -= 8 if signal != OptionBias.NO_TRADE else 0
    return max(0, min(100, int(round(base))))


def _risk_plan(signal: OptionBias, payload: NarrativeInput, support: float | None, resistance: float | None) -> RiskPlan:
    spot = payload.spot_price
    if signal == OptionBias.BUY_CE:
        level = resistance or spot
        return RiskPlan(
            entry=f"Buy CE only above sustained spot {level:.2f}",
            stop_loss=f"Exit if spot closes below {level:.2f}",
            targets=[f"{spot + max(40.0, spot * 0.003):.2f}", f"{spot + max(80.0, spot * 0.006):.2f}"],
            risk_reward="Minimum 1:1.5 after premium spread and slippage.",
        )
    if signal == OptionBias.BUY_PE:
        level = support or spot
        return RiskPlan(
            entry=f"Buy PE only below sustained spot {level:.2f}",
            stop_loss=f"Exit if spot closes above {level:.2f}",
            targets=[f"{spot - max(40.0, spot * 0.003):.2f}", f"{spot - max(80.0, spot * 0.006):.2f}"],
            risk_reward="Minimum 1:1.5 after premium spread and slippage.",
        )
    return RiskPlan(
        entry="No fresh entry while price is inside range or confirmation is incomplete.",
        stop_loss="No trade stop. Re-evaluate after confirmed range break.",
        targets=[],
        risk_reward="Capital preservation; avoid theta bleed.",
    )


def _option_strike_suggestion(signal: OptionBias, payload: NarrativeInput) -> str:
    if signal == OptionBias.NO_TRADE:
        return "No option strike. Wait for confirmation."
    if payload.is_expiry_day or (payload.days_to_expiry is not None and payload.days_to_expiry <= 0):
        return "ATM or ITM only; avoid far OTM on expiry day."
    return "ATM or slightly ITM for 1-3 day holding."


def _expiry_warning(payload: NarrativeInput, regime: MarketRegime) -> str:
    if payload.is_expiry_day or (payload.days_to_expiry is not None and payload.days_to_expiry <= 0):
        return "Expiry day: theta decay, whipsaw and premium crush risk are high; avoid far OTM options."
    if regime == MarketRegime.VOLATILE:
        return "VIX/volatility risk: premium can expand and reverse quickly; use smaller size."
    return "Monitor theta decay and avoid holding OTM premium without follow-through."


def _invalidation_level(signal: OptionBias, payload: NarrativeInput, support: float | None, resistance: float | None) -> float | None:
    if signal == OptionBias.BUY_CE:
        return resistance
    if signal == OptionBias.BUY_PE:
        return support
    if support and payload.spot_price < support:
        return support
    if resistance and payload.spot_price > resistance:
        return resistance
    return None


def _futures_premium_pct(payload: NarrativeInput) -> float:
    if payload.futures_price is None:
        return 0.0
    return (float(payload.futures_price) - float(payload.spot_price)) / max(float(payload.spot_price), 1.0) * 100.0


def _vix_rising(payload: NarrativeInput) -> bool:
    return _coalesce(payload.india_vix_change_pct, 0.0) > 3.0


def _optional_number(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float:
    return _optional_number(value) or 0.0


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
