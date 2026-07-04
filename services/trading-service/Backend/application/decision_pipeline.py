from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any

from Backend.application.decision_engine import DecisionEngine, DecisionInputs, TradingDecision
from Backend.application.recommendation_store import recommendation_metrics, record_recommendation


@dataclass(frozen=True, slots=True)
class MarketDataInputs:
    symbol: str = "NIFTY"
    market_live: bool = False
    valid_for_execution: bool = False
    feed_delay_seconds: int | float = 0
    warnings: list[str] = field(default_factory=list)
    candles: list[dict[str, Any]] = field(default_factory=list)
    trend: str | None = None
    momentum: str | None = None
    price_action: str | None = None
    support: str = "Nearest confirmed demand zone"
    resistance: str = "Nearest confirmed supply zone"
    oi_bias: str | None = None
    pcr: float | None = None
    max_pain: str | None = None
    india_vix: float | None = None
    fii_dii_bias: str | None = None
    gift_nifty_bias: str | None = None
    vwap_relation: str | None = None
    liquidity: str | None = None
    expiry_day: bool = False
    capital: float = 100000.0
    risk_per_trade: float = 1500.0
    lot_size: int = 50


@dataclass(frozen=True, slots=True)
class TrendAnalysis:
    trend_direction: str
    trend_strength: int
    supporting_evidence: list[str]
    warning_if_sideways: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trend_direction": self.trend_direction,
            "trend_strength": self.trend_strength,
            "supporting_evidence": self.supporting_evidence,
            "warning_if_sideways": self.warning_if_sideways,
        }


@dataclass(frozen=True, slots=True)
class EMAAnalysis:
    ema_bias: str
    ema_strength: int
    reason: str
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ema_bias": self.ema_bias, "ema_strength": self.ema_strength, "reason": self.reason, "warning": self.warning}


@dataclass(frozen=True, slots=True)
class VolumeAnalysis:
    volume_status: str
    volume_strength: int
    supports_trade: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_status": self.volume_status,
            "volume_strength": self.volume_strength,
            "supports_trade": self.supports_trade,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SupportResistanceAnalysis:
    support: float | None
    resistance: float | None
    entry_zone: str
    invalidation_level: str
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "support": self.support,
            "resistance": self.resistance,
            "entry_zone": self.entry_zone,
            "invalidation_level": self.invalidation_level,
            "warning": self.warning,
        }


@dataclass(frozen=True, slots=True)
class RiskRewardAnalysis:
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    position_size: int
    allowed: bool
    warnings: list[str]
    stop_loss: float | None
    target: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_amount": self.risk_amount,
            "reward_amount": self.reward_amount,
            "risk_reward_ratio": self.risk_reward_ratio,
            "position_size": self.position_size,
            "allowed": self.allowed,
            "warnings": self.warnings,
            "stop_loss": self.stop_loss,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class DecisionPipelineResult:
    decision: TradingDecision
    factors: dict[str, Any]
    analytics: dict[str, Any]
    decision_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "factors": self.factors,
            "analytics": self.analytics,
            "decision_id": self.decision_id,
        }


class DecisionPipelineService:
    def __init__(self, decision_engine: DecisionEngine | None = None) -> None:
        self.decision_engine = decision_engine or DecisionEngine()

    def run(
        self,
        market: MarketDataInputs,
        *,
        risk_blocked: bool,
        confidence_threshold: int = 70,
        persist: bool = True,
    ) -> DecisionPipelineResult:
        factors = self._map_factors(market)
        warnings = [*market.warnings, *factors["checklist_blockers"]]
        decision = self.decision_engine.decide(
            DecisionInputs(
                market_live=market.market_live,
                valid_for_execution=market.valid_for_execution,
                risk_blocked=risk_blocked or bool(factors["checklist_blockers"]),
                feed_delay_seconds=market.feed_delay_seconds,
                warnings=warnings,
                market_bias=factors["market_bias"],
                market_trend=factors["trend"],
                momentum=factors["momentum"],
                price_action=factors["price_action"],
                support=factors["support"],
                resistance=factors["resistance"],
                oi_bias=factors["oi_bias"],
                pcr=factors["pcr"],
                vix=factors["india_vix"],
                fii_dii_bias=factors["fii_dii_bias"],
                max_pain=factors["max_pain"],
                vwap_relation=factors["vwap_relation"],
                gift_nifty_bias=factors["gift_nifty_bias"],
                liquidity=factors["liquidity"],
                expiry_day=market.expiry_day,
                confidence_threshold=confidence_threshold,
            )
        )
        decision = self._apply_checklist_outputs(decision, factors)
        decision_id = ""
        if persist:
            row = record_recommendation(market.symbol, decision, {"decision": decision.to_dict(), "factors": factors})
            decision_id = row["decision_id"]
        return DecisionPipelineResult(
            decision=decision,
            factors=factors,
            analytics=recommendation_metrics(),
            decision_id=decision_id,
        )

    @staticmethod
    def _apply_checklist_outputs(decision: TradingDecision, factors: dict[str, Any]) -> TradingDecision:
        sr = factors["support_resistance"]
        rr = factors["risk_reward"]
        checklist = f"Checklist score {factors['checklist_score']}/100."
        blockers = factors["checklist_blockers"]
        explanation = decision.simple_explanation
        if blockers:
            explanation = f"No Trade because {blockers[0]}"
        elif decision.trade_recommendation == "Buy CE":
            explanation = f"Trend supports CE. {factors['ema_analysis']['reason']} {factors['volume_analysis']['reason']} Risk reward is acceptable."
        elif decision.trade_recommendation == "Buy PE":
            explanation = f"Trend supports PE. {factors['ema_analysis']['reason']} {factors['volume_analysis']['reason']} Risk reward is acceptable."
        return replace(
            decision,
            entry_zone=sr["entry_zone"],
            stop_loss=str(rr["stop_loss"] if rr["stop_loss"] is not None else decision.stop_loss),
            target=str(rr["target"] if rr["target"] is not None else decision.target),
            invalidation_level=sr["invalidation_level"],
            simple_explanation=f"{explanation} {checklist}",
            warnings=[*decision.warnings, *[item for item in blockers if item not in decision.warnings], *rr["warnings"]],
            score_reason=f"{decision.score_reason} {checklist}",
        )

    def from_environment(self, *, validation: Any, candles: list[dict[str, Any]] | None = None, symbol: str = "NIFTY") -> MarketDataInputs:
        return MarketDataInputs(
            symbol=symbol,
            market_live=bool(getattr(validation, "market_live", False)),
            valid_for_execution=bool(getattr(validation, "valid_for_execution", False)),
            feed_delay_seconds=getattr(validation, "delay_seconds", 0) or 0,
            warnings=list(getattr(validation, "warnings", []) or []),
            candles=candles or [],
            trend=os.getenv("MARKET_TREND"),
            momentum=os.getenv("MOMENTUM_BIAS"),
            price_action=os.getenv("PRICE_ACTION"),
            support=os.getenv("SUPPORT_LEVEL", "Nearest confirmed demand zone"),
            resistance=os.getenv("RESISTANCE_LEVEL", "Nearest confirmed supply zone"),
            oi_bias=os.getenv("OI_BIAS"),
            pcr=_float_env("PCR"),
            max_pain=os.getenv("MAX_PAIN"),
            india_vix=_float_env("INDIA_VIX"),
            fii_dii_bias=os.getenv("FII_DII_BIAS"),
            gift_nifty_bias=os.getenv("GIFT_NIFTY_BIAS"),
            vwap_relation=os.getenv("VWAP_RELATION"),
            liquidity=os.getenv("LIQUIDITY_STATUS"),
            expiry_day=_bool_env("EXPIRY_DAY"),
        )

    def _map_factors(self, market: MarketDataInputs) -> dict[str, Any]:
        trend_analysis = analyze_trend(market.candles)
        ema_analysis = analyze_ema(market.candles)
        volume_analysis = analyze_volume(market.candles)
        sr_analysis = analyze_support_resistance(market.candles)
        trend = _normalize_bias(market.trend) or _bias_from_direction(trend_analysis.trend_direction)
        momentum = _normalize_bias(market.momentum) or self._momentum_from_candles(market.candles)
        vwap_relation = market.vwap_relation or self._vwap_relation(market.candles)
        risk_reward = analyze_risk_reward(market, trend or "NEUTRAL", sr_analysis)
        directional_votes = [
            trend,
            momentum,
            ema_analysis.ema_bias,
            _normalize_bias(market.price_action),
            _normalize_bias(market.oi_bias),
            _normalize_bias(market.fii_dii_bias),
            _normalize_bias(market.gift_nifty_bias),
        ]
        market_bias = _majority_bias(directional_votes)
        blockers = _checklist_blockers(market, trend_analysis, ema_analysis, volume_analysis, sr_analysis, risk_reward)
        if blockers:
            market_bias = "NEUTRAL"
        checklist_score = _checklist_score(trend_analysis, ema_analysis, volume_analysis, sr_analysis, risk_reward, blockers)
        checklist = _technical_checklist(
            market,
            checklist_score,
            blockers,
            trend_analysis,
            ema_analysis,
            volume_analysis,
            sr_analysis,
            risk_reward,
        )
        return {
            "market_bias": market_bias,
            "trend": trend,
            "momentum": momentum,
            "price_action": _normalize_bias(market.price_action),
            "support": str(sr_analysis.support) if sr_analysis.support is not None else market.support,
            "resistance": str(sr_analysis.resistance) if sr_analysis.resistance is not None else market.resistance,
            "oi_bias": _normalize_bias(market.oi_bias),
            "pcr": market.pcr,
            "max_pain": market.max_pain,
            "india_vix": market.india_vix,
            "fii_dii_bias": _normalize_bias(market.fii_dii_bias),
            "gift_nifty_bias": _normalize_bias(market.gift_nifty_bias),
            "vwap_relation": vwap_relation,
            "liquidity": market.liquidity,
            "expiry_day": market.expiry_day,
            "data_freshness_seconds": market.feed_delay_seconds,
            "checklist": checklist,
            "checklist_score": checklist_score,
            "checklist_blockers": blockers,
            "trend_analysis": trend_analysis.to_dict(),
            "ema_analysis": ema_analysis.to_dict(),
            "volume_analysis": volume_analysis.to_dict(),
            "support_resistance": sr_analysis.to_dict(),
            "risk_reward": risk_reward.to_dict(),
        }

    @staticmethod
    def _trend_from_candles(candles: list[dict[str, Any]]) -> str:
        if len(candles) < 2:
            return "NEUTRAL"
        first = float(candles[0].get("close") or 0)
        last = float(candles[-1].get("close") or 0)
        if last > first:
            return "BULLISH"
        if last < first:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _momentum_from_candles(candles: list[dict[str, Any]]) -> str:
        if len(candles) < 4:
            return "NEUTRAL"
        recent = candles[-4:]
        closes = [float(candle.get("close") or 0) for candle in recent]
        if closes[-1] > closes[0] and closes[-1] >= max(closes[:-1]):
            return "BULLISH"
        if closes[-1] < closes[0] and closes[-1] <= min(closes[:-1]):
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _vwap_relation(candles: list[dict[str, Any]]) -> str | None:
        if not candles:
            return None
        latest = candles[-1]
        close = float(latest.get("close") or 0)
        vwap = latest.get("vwap")
        if vwap is None:
            return None
        return "above VWAP" if close >= float(vwap) else "below VWAP"


def analyze_trend(candles: list[dict[str, Any]]) -> TrendAnalysis:
    if len(candles) < 5:
        return TrendAnalysis("SIDEWAYS", 20, ["Need at least 5 candles for structure."], "Market structure is unclear.")
    recent = candles[-8:]
    highs = [_num(candle.get("high", candle.get("close"))) for candle in recent]
    lows = [_num(candle.get("low", candle.get("close"))) for candle in recent]
    higher_highs = sum(1 for prev, cur in zip(highs, highs[1:]) if cur > prev)
    higher_lows = sum(1 for prev, cur in zip(lows, lows[1:]) if cur > prev)
    lower_highs = sum(1 for prev, cur in zip(highs, highs[1:]) if cur < prev)
    lower_lows = sum(1 for prev, cur in zip(lows, lows[1:]) if cur < prev)
    evidence = [
        f"Higher highs: {higher_highs}",
        f"Higher lows: {higher_lows}",
        f"Lower highs: {lower_highs}",
        f"Lower lows: {lower_lows}",
    ]
    if higher_highs >= 4 and higher_lows >= 4:
        return TrendAnalysis("UPTREND", min(100, 45 + (higher_highs + higher_lows) * 7), evidence)
    if lower_highs >= 4 and lower_lows >= 4:
        return TrendAnalysis("DOWNTREND", min(100, 45 + (lower_highs + lower_lows) * 7), evidence)
    return TrendAnalysis("SIDEWAYS", 35, evidence, "Trend is sideways; avoid forcing CE or PE.")


def analyze_ema(candles: list[dict[str, Any]]) -> EMAAnalysis:
    closes = [_num(candle.get("close")) for candle in candles]
    if len(closes) < 50:
        return EMAAnalysis("NEUTRAL", 25, "Need at least 50 candles for 20 EMA and 50 EMA.", "EMA signal is weak.")
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    price = closes[-1]
    if price > ema20 > ema50:
        return EMAAnalysis("BULLISH", 85, "Price above 20 EMA and 50 EMA; 20 EMA is above 50 EMA.")
    if price < ema20 < ema50:
        return EMAAnalysis("BEARISH", 85, "Price below 20 EMA and 50 EMA; 20 EMA is below 50 EMA.")
    if price > ema20 and price > ema50:
        return EMAAnalysis("BULLISH", 65, "Price is above both EMAs, but EMA structure is not fully aligned.")
    if price < ema20 and price < ema50:
        return EMAAnalysis("BEARISH", 65, "Price is below both EMAs, but EMA structure is not fully aligned.")
    return EMAAnalysis("NEUTRAL", 35, "Price is between 20 EMA and 50 EMA.", "EMA signal is weak; avoid.")


def analyze_volume(candles: list[dict[str, Any]]) -> VolumeAnalysis:
    if len(candles) < 6:
        return VolumeAnalysis("LOW_DATA", 20, False, "Need more candles for volume confirmation.")
    volumes = [_num(candle.get("volume")) for candle in candles[-21:]]
    latest_volume = volumes[-1]
    average = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
    latest = candles[-1]
    previous = candles[-2]
    breakout = _num(latest.get("close")) > max(_num(candle.get("high", candle.get("close"))) for candle in candles[-6:-1])
    breakdown = _num(latest.get("close")) < min(_num(candle.get("low", candle.get("close"))) for candle in candles[-6:-1])
    green = _num(latest.get("close")) >= _num(previous.get("close"))
    if latest_volume >= average * 1.5 and (breakout or breakdown):
        status = "BREAKOUT_CONFIRMED" if breakout and green else "BREAKDOWN_CONFIRMED"
        return VolumeAnalysis(status, 90, True, "Volume confirms breakout." if breakout else "Volume confirms breakdown.")
    if latest_volume >= average * 1.8:
        return VolumeAnalysis("VOLUME_SPIKE", 70, True, "Volume spike supports active participation.")
    if latest_volume < average * 0.8:
        return VolumeAnalysis("LOW_VOLUME_MOVE", 35, False, "Volume does not confirm the move.")
    return VolumeAnalysis("NORMAL", 55, True, "Volume is near average.")


def analyze_support_resistance(candles: list[dict[str, Any]]) -> SupportResistanceAnalysis:
    if len(candles) < 5:
        return SupportResistanceAnalysis(None, None, "Wait for support/resistance to form", "No active view", "Need more candles for support/resistance.")
    current = _num(candles[-1].get("close"))
    lows = sorted({_num(candle.get("low", candle.get("close"))) for candle in candles[-30:] if _num(candle.get("low", candle.get("close"))) < current})
    highs = sorted({_num(candle.get("high", candle.get("close"))) for candle in candles[-30:] if _num(candle.get("high", candle.get("close"))) > current})
    support = lows[-1] if lows else min(_num(candle.get("low", candle.get("close"))) for candle in candles[-30:])
    resistance = highs[0] if highs else max(_num(candle.get("high", candle.get("close"))) for candle in candles[-30:])
    range_size = max(resistance - support, 0.01)
    support_distance = (current - support) / range_size
    resistance_distance = (resistance - current) / range_size
    warning = None
    if resistance_distance < 0.2:
        warning = "Price is near resistance; avoid chasing CE."
    if support_distance < 0.2:
        warning = "Price is near support; avoid chasing PE."
    return SupportResistanceAnalysis(
        round(support, 2),
        round(resistance, 2),
        f"{round(support, 2)} to {round(current, 2)}" if support_distance <= 0.5 else "Wait for pullback near support",
        str(round(support, 2)) if support_distance <= resistance_distance else str(round(resistance, 2)),
        warning,
    )


def analyze_risk_reward(market: MarketDataInputs, bias: str, sr: SupportResistanceAnalysis) -> RiskRewardAnalysis:
    if not market.candles or sr.support is None or sr.resistance is None:
        return RiskRewardAnalysis(0, 0, 0, 0, False, ["Stop loss and target need support/resistance."], None, None)
    entry = _num(market.candles[-1].get("close"))
    bullish = bias == "BULLISH"
    stop = sr.support if bullish else sr.resistance
    target = sr.resistance if bullish else sr.support
    risk_per_unit = abs(entry - stop)
    reward_per_unit = abs(target - entry)
    warnings: list[str] = []
    if risk_per_unit <= 0:
        warnings.append("Stop loss is not valid.")
    if reward_per_unit <= 0:
        warnings.append("Target is not valid.")
    ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0.0
    risk_budget = min(float(market.risk_per_trade), float(market.capital) * 0.02)
    position_size = int(risk_budget / risk_per_unit) if risk_per_unit > 0 else 0
    if market.lot_size > 1:
        position_size = max(0, position_size - (position_size % int(market.lot_size)))
    if ratio < 1.5:
        warnings.append("Risk reward is below 1.5.")
    if position_size <= 0:
        warnings.append("Position size is zero under configured risk.")
    return RiskRewardAnalysis(
        round(risk_per_unit * max(position_size, 1), 2),
        round(reward_per_unit * max(position_size, 1), 2),
        round(ratio, 2),
        position_size,
        ratio >= 1.5 and position_size > 0 and not any("not valid" in item for item in warnings),
        warnings,
        round(stop, 2),
        round(target, 2),
    )


def _checklist_blockers(
    market: MarketDataInputs,
    trend: TrendAnalysis,
    ema: EMAAnalysis,
    volume: VolumeAnalysis,
    sr: SupportResistanceAnalysis,
    rr: RiskRewardAnalysis,
) -> list[str]:
    blockers: list[str] = []
    if not market.valid_for_execution:
        blockers.append("data is stale")
    if trend.trend_direction == "SIDEWAYS":
        blockers.append("trend is sideways")
    if ema.ema_bias == "NEUTRAL":
        blockers.append("EMA signal is weak")
    if not volume.supports_trade:
        blockers.append("volume does not confirm")
    if sr.warning:
        blockers.append(sr.warning)
    if not rr.allowed:
        blockers.append("risk reward is poor")
    if market.india_vix is not None and market.india_vix >= 22:
        blockers.append("VIX is elevated")
    if _normalize_bias(market.oi_bias) and _normalize_bias(market.oi_bias) not in {ema.ema_bias, "NEUTRAL"}:
        blockers.append("OI is conflicting")
    return blockers


def _checklist_score(
    trend: TrendAnalysis,
    ema: EMAAnalysis,
    volume: VolumeAnalysis,
    sr: SupportResistanceAnalysis,
    rr: RiskRewardAnalysis,
    blockers: list[str],
) -> int:
    score = 0
    score += 20 if trend.trend_direction != "SIDEWAYS" else 5
    score += min(20, int(ema.ema_strength / 5))
    score += 20 if volume.supports_trade else 5
    score += 20 if not sr.warning and sr.support is not None and sr.resistance is not None else 8
    score += 20 if rr.allowed else 5
    return max(0, min(100, score - min(25, len(blockers) * 5)))


def _technical_checklist(
    market: MarketDataInputs,
    checklist_score: int,
    blockers: list[str],
    trend: TrendAnalysis,
    ema: EMAAnalysis,
    volume: VolumeAnalysis,
    sr: SupportResistanceAnalysis,
    rr: RiskRewardAnalysis,
) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = list(blockers)
    warnings: list[str] = list(market.warnings)

    if trend.trend_direction != "SIDEWAYS":
        passed.append(f"Trend supports {'CE' if trend.trend_direction == 'UPTREND' else 'PE'}.")
    if ema.ema_bias != "NEUTRAL":
        passed.append(ema.reason)
    if volume.supports_trade:
        passed.append(volume.reason)
    if sr.support is not None and sr.resistance is not None and not sr.warning:
        passed.append("Support and resistance are usable.")
    if rr.allowed:
        passed.append("Risk reward is acceptable.")
    if market.valid_for_execution:
        passed.append("Data is fresh enough for execution checks.")
    if market.india_vix is None or market.india_vix < 22:
        passed.append("VIX is inside risk limits.")

    if trend.warning_if_sideways:
        warnings.append(trend.warning_if_sideways)
    if ema.warning:
        warnings.append(ema.warning)
    if sr.warning:
        warnings.append(sr.warning)
    warnings.extend(rr.warnings)

    return {
        "checklist_score": checklist_score,
        "passed": _dedupe(passed),
        "failed": _dedupe(failed),
        "warnings": _dedupe(warnings),
        "trend": trend.to_dict(),
        "ema": ema.to_dict(),
        "volume": volume.to_dict(),
        "support_resistance": sr.to_dict(),
        "risk_reward": rr.to_dict(),
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _bias_from_direction(direction: str) -> str:
    if direction == "UPTREND":
        return "BULLISH"
    if direction == "DOWNTREND":
        return "BEARISH"
    return "NEUTRAL"


def _ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = (price - value) * multiplier + value
    return value


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_bias(value: str | None) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"BULLISH", "BEARISH", "NEUTRAL"} else None


def _majority_bias(values: list[str | None]) -> str:
    bullish = sum(1 for value in values if value == "BULLISH")
    bearish = sum(1 for value in values if value == "BEARISH")
    if bullish >= bearish + 2:
        return "BULLISH"
    if bearish >= bullish + 2:
        return "BEARISH"
    return "NEUTRAL"


def _float_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw in {None, ""}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _bool_env(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}
