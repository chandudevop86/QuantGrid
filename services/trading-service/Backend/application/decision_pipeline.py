from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from Backend.application.decision_engine import DecisionEngine, DecisionInputs, TradingDecision
from Backend.application.recommendation_store import recommendation_metrics, record_recommendation
from Backend.application.volume_analysis import analyze_volume as analyze_institutional_volume
from Backend.domain.engine.strategy_engine import StrategyEngine


@dataclass(frozen=True, slots=True)
class MarketDataInputs:
    symbol: str = "NIFTY"
    market_live: bool = False
    valid_for_execution: bool = False
    feed_delay_seconds: int | float = 0
    warnings: list[str] = field(default_factory=list)
    candles: list[dict[str, Any]] = field(default_factory=list)
    candles_1m: list[dict[str, Any]] = field(default_factory=list)
    candles_5m: list[dict[str, Any]] = field(default_factory=list)
    candles_15m: list[dict[str, Any]] = field(default_factory=list)
    candles_1h: list[dict[str, Any]] = field(default_factory=list)
    candles_daily: list[dict[str, Any]] = field(default_factory=list)
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
    call_oi: float | None = None
    put_oi: float | None = None
    oi_change: str | None = None
    iv: float | None = None
    fii_cash: float | None = None
    dii_cash: float | None = None
    fii_futures: float | None = None
    usdinr_bias: str | None = None
    crude_bias: str | None = None
    global_markets_bias: str | None = None
    gap_pct: float = 0.0
    news_driven: bool = False
    holiday_effect: bool = False
    trades_today: int = 0
    max_trades_per_day: int = 3
    consecutive_losses: int = 0
    max_consecutive_losses: int = 3
    duplicate_signal: bool = False
    context_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    enforce_data_quality: bool = False


@dataclass(frozen=True, slots=True)
class TradeDataQualityResult:
    quality_score: int
    usable_for_trade: bool
    status: str
    critical_errors: list[str]
    warnings: list[str]
    components: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_score": self.quality_score,
            "usable_for_trade": self.usable_for_trade,
            "status": self.status,
            "critical_errors": self.critical_errors,
            "warnings": self.warnings,
            "components": self.components,
        }


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
    institutional_buying: bool = False
    institutional_selling: bool = False
    relative_volume: float = 0.0
    smart_money_score: int = 0
    volume_confidence: int = 0
    signal: str = "NO TRADE"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_status": self.volume_status,
            "volume_strength": self.volume_strength,
            "supports_trade": self.supports_trade,
            "reason": self.reason,
            "institutional_buying": self.institutional_buying,
            "institutional_selling": self.institutional_selling,
            "relative_volume": self.relative_volume,
            "smart_money_score": self.smart_money_score,
            "volume_confidence": self.volume_confidence,
            "signal": self.signal,
            "details": self.details,
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
    def __init__(self, decision_engine: DecisionEngine | None = None, strategy_engine: StrategyEngine | None = None) -> None:
        self.decision_engine = decision_engine or DecisionEngine()
        self.strategy_engine = strategy_engine or StrategyEngine()

    def run(
        self,
        market: MarketDataInputs,
        *,
        risk_blocked: bool,
        confidence_threshold: int = 70,
        persist: bool = True,
    ) -> DecisionPipelineResult:
        factors = self._map_factors(market, risk_blocked=risk_blocked)
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
        final_decision = factors.get("final_decision") or {}
        explanation = decision.simple_explanation
        if (final_decision.get("explainability") or {}).get("plain_english"):
            explanation = final_decision["explainability"]["plain_english"]
        elif blockers:
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

    def from_environment(
        self,
        *,
        validation: Any,
        candles: list[dict[str, Any]] | None = None,
        candles_by_interval: dict[str, list[dict[str, Any]]] | None = None,
        market_context: dict[str, dict[str, Any]] | None = None,
        enforce_data_quality: bool = False,
        symbol: str = "NIFTY",
    ) -> MarketDataInputs:
        candles = candles or []
        candles_by_interval = candles_by_interval or {}
        context_values, context_status, context_warnings = _verified_market_context(market_context or {})
        return MarketDataInputs(
            symbol=symbol,
            market_live=bool(getattr(validation, "market_live", False)),
            valid_for_execution=bool(getattr(validation, "valid_for_execution", False)),
            feed_delay_seconds=getattr(validation, "delay_seconds", 0) or 0,
            warnings=[*list(getattr(validation, "warnings", []) or []), *context_warnings],
            candles=candles,
            candles_1m=candles_by_interval.get("1m", candles),
            candles_5m=candles_by_interval.get("5m", []),
            candles_15m=candles_by_interval.get("15m", []),
            candles_1h=candles_by_interval.get("1h", []),
            candles_daily=candles_by_interval.get("1d", []),
            trend=_context_text(context_values, "trend"),
            momentum=_context_text(context_values, "momentum"),
            price_action=_context_text(context_values, "price_action"),
            oi_bias=_context_text(context_values, "oi_bias"),
            pcr=_context_number(context_values, "pcr"),
            max_pain=_context_text(context_values, "max_pain"),
            india_vix=_context_number(context_values, "india_vix"),
            fii_dii_bias=_context_text(context_values, "fii_dii_bias"),
            gift_nifty_bias=_context_text(context_values, "gift_nifty_bias"),
            vwap_relation=_context_text(context_values, "vwap_relation"),
            liquidity=_context_text(context_values, "liquidity"),
            call_oi=_context_number(context_values, "call_oi"),
            put_oi=_context_number(context_values, "put_oi"),
            iv=_context_number(context_values, "iv"),
            expiry_day=bool(context_values.get("expiry_day", False)),
            context_status=context_status,
            enforce_data_quality=enforce_data_quality,
        )

    def _map_factors(self, market: MarketDataInputs, *, risk_blocked: bool = False) -> dict[str, Any]:
        base_candles = market.candles or market.candles_1m
        trend_analysis = analyze_trend(base_candles)
        ema_analysis = analyze_ema(base_candles)
        volume_analysis = analyze_volume(base_candles)
        sr_analysis = analyze_support_resistance(base_candles)
        htf_analysis = analyze_higher_timeframe(market)
        data_quality = assess_trade_data_quality(market, htf_analysis)
        market_structure = analyze_market_structure(base_candles, volume_analysis)
        key_levels = analyze_key_levels(base_candles)
        supply_demand = analyze_supply_demand(base_candles)
        fvg_analysis = analyze_fvg(base_candles, trend_analysis, key_levels)
        liquidity = analyze_liquidity(base_candles, sr_analysis)
        price_action = analyze_price_action(base_candles)
        regime = analyze_market_regime(market, volume_analysis, trend_analysis)
        options_flow = analyze_options_flow(market)
        institutional = analyze_institutional_filter(market)
        discipline = analyze_discipline(market, trend_analysis, sr_analysis, price_action, ema_analysis)
        trend = _normalize_bias(market.trend) or _bias_from_direction(trend_analysis.trend_direction)
        momentum = _normalize_bias(market.momentum) or self._momentum_from_candles(base_candles)
        vwap_relation = market.vwap_relation or self._vwap_relation(base_candles)
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
        blockers.extend(_high_probability_blockers(htf_analysis, price_action, discipline, options_flow, institutional, regime))
        blockers.extend(data_quality.critical_errors)
        blockers = _dedupe(blockers)
        if blockers:
            market_bias = "NEUTRAL"
        confluence = _confluence_engine(
            trend_analysis,
            htf_analysis,
            supply_demand,
            fvg_analysis,
            liquidity,
            price_action,
            volume_analysis,
            options_flow,
            institutional,
            risk_reward,
            discipline,
        )
        trade_confidence = _trade_confidence_contract(market, confluence)
        strategy_selection = _strategy_selection_engine(regime, market_structure, price_action, volume_analysis, risk_reward, confluence, self.strategy_engine.registry())
        probability = _probability_engine(confluence, regime, options_flow, institutional, risk_reward)
        checklist_score = confluence["confluence_score"]
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
        checklist.update(
            {
                "htf": htf_analysis,
                "market_structure": market_structure,
                "key_levels": key_levels,
                "supply_demand": supply_demand,
                "fvg": fvg_analysis,
                "liquidity": liquidity,
                "price_action": price_action,
                "market_regime": regime,
                "strategy_selection": strategy_selection,
                "options_flow": options_flow,
                "institutional": institutional,
                "discipline": discipline,
                "confluence_engine": confluence,
                "confidence_engine": {
                    "confidence_score": confluence["confluence_score"],
                    "weights": confluence["weights"],
                    "breakdown": confluence["breakdown"],
                    "trade_confidence": trade_confidence,
                },
                "data_quality": data_quality.to_dict(),
            }
        )
        final_decision = _final_decision_payload(
            market,
            checklist_score,
            blockers,
            checklist,
            market_bias,
            risk_reward,
            sr_analysis,
            confluence,
            strategy_selection,
            probability,
        )
        final_decision["trade_confidence"] = trade_confidence
        paper_trade_gate = _paper_trade_gate(market, final_decision, risk_reward, discipline, confluence, risk_blocked)
        eligible = bool(paper_trade_gate["allowed"] and final_decision["trade_decision"] != "No Trade")
        final_decision["trade_eligibility"] = {
            "eligible": eligible,
            "mode": "paper",
            "status": "ELIGIBLE" if eligible else "BLOCKED",
            "reasons": [] if eligible else list(paper_trade_gate["reasons"]),
        }
        final_decision["trade_plan"] = (
            {
                "decision": final_decision["trade_decision"],
                "entry_zone": final_decision["entry_zone"],
                "stop_loss": final_decision["stop_loss"],
                "target": final_decision["target"],
                "invalidation_level": final_decision["invalidation_level"],
                "risk_reward_ratio": final_decision["risk_reward_ratio"],
                "position_size": final_decision["position_size"],
            }
            if eligible
            else None
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
            "market_context_status": market.context_status,
            "data_quality": data_quality.to_dict(),
            "checklist": checklist,
            "checklist_score": checklist_score,
            "checklist_blockers": blockers,
            "confluence_engine": confluence,
            "probability_engine": probability,
            "strategy_selection": strategy_selection,
            "final_decision": final_decision,
            "high_probability_trade_engine": {
                "layers": {
                    "market_structure": trend_analysis.to_dict(),
                    "structure": market_structure,
                    "higher_timeframe": htf_analysis,
                    "key_levels": key_levels,
                    "supply_demand": supply_demand,
                    "fvg": fvg_analysis,
                    "liquidity": liquidity,
                    "price_action": price_action,
                    "market_regime": regime,
                    "strategy_selection": strategy_selection,
                    "options_flow": options_flow,
                    "institutional": institutional,
                    "risk_management": risk_reward.to_dict(),
                    "discipline": discipline,
                    "confluence": confluence,
                },
                "paper_trade_allowed": paper_trade_gate["allowed"],
                "paper_trade_gate": paper_trade_gate,
            },
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
    try:
        institutional = analyze_institutional_volume(
            symbol="NIFTY",
            timeframe="pipeline",
            candles=_candles_with_timestamps(candles),
        ).to_dict()
    except Exception:
        return _legacy_volume_analysis(candles)
    status = "NORMAL"
    if institutional["breakout_confirmation"]:
        status = "BREAKOUT_CONFIRMED"
    elif institutional["breakdown_confirmation"]:
        status = "BREAKDOWN_CONFIRMED"
    elif institutional["volume_spike"]:
        status = "VOLUME_SPIKE"
    elif institutional["relative_volume"] < 0.8:
        status = "LOW_VOLUME_MOVE"

    supports_trade = bool(
        institutional["volume_confidence"] >= 45
        and institutional["signal"] in {"BUY", "SELL", "WAIT"}
        and status != "LOW_VOLUME_MOVE"
    )
    return VolumeAnalysis(
        status,
        int(institutional["volume_confidence"]),
        supports_trade,
        str(institutional["reason"]),
        institutional_buying=bool(institutional["institutional_buying"] or institutional["breakout_confirmation"]),
        institutional_selling=bool(institutional["institutional_selling"] or institutional["breakdown_confirmation"]),
        relative_volume=float(institutional["relative_volume"]),
        smart_money_score=int(institutional["smart_money_score"]),
        volume_confidence=int(institutional["volume_confidence"]),
        signal=str(institutional["signal"]),
        details={
            "current_volume": institutional["current_volume"],
            "average_volume_20": institutional["average_volume_20"],
            "average_volume_50": institutional["average_volume_50"],
            "volume_ratio": institutional["volume_ratio"],
            "volume_trend": institutional["volume_trend"],
            "delivery_percentage": institutional["delivery_percentage"],
            "volume_spike": institutional["volume_spike"],
            "breakout_confirmation": institutional["breakout_confirmation"],
            "breakdown_confirmation": institutional["breakdown_confirmation"],
            "accumulation": institutional["accumulation"],
            "distribution": institutional["distribution"],
            "obv": institutional["obv"],
            "vwap": institutional["vwap"],
            "cmf": institutional["cmf"],
            "ad_line": institutional["ad_line"],
            "volume_profile": institutional["volume_profile"],
            "ai_summary": institutional["ai_summary"],
        },
    )


def _legacy_volume_analysis(candles: list[dict[str, Any]]) -> VolumeAnalysis:
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


def _candles_with_timestamps(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    normalized: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        row = dict(candle)
        row.setdefault("timestamp", (start + timedelta(minutes=index)).isoformat())
        normalized.append(row)
    return normalized


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


def assess_trade_data_quality(market: MarketDataInputs, htf: dict[str, Any]) -> TradeDataQualityResult:
    if not market.enforce_data_quality:
        return TradeDataQualityResult(
            quality_score=100,
            usable_for_trade=True,
            status="NOT_ASSESSED",
            critical_errors=[],
            warnings=["Central data-quality enforcement was not requested by this legacy caller."],
            components={},
        )

    from app.validation.data_quality import validate_candles

    series = {
        "TimeFrame.M1": market.candles_1m or market.candles,
        "TimeFrame.M5": market.candles_5m,
        "TimeFrame.M15": market.candles_15m,
        "TimeFrame.H1": market.candles_1h,
        "TimeFrame.D1": market.candles_daily,
    }
    required = {"TimeFrame.M1", "TimeFrame.M15", "TimeFrame.H1"}
    critical_errors: list[str] = []
    warnings: list[str] = []
    components: dict[str, dict[str, Any]] = {}
    scores: list[int] = []

    for timeframe, candles in series.items():
        _valid, report = validate_candles(candles, source="stored-live-cache" if candles else "unavailable")
        payload = report.model_dump()
        integrity = _candle_series_integrity(candles, timeframe)
        payload["series_integrity"] = integrity
        components[f"candles_{timeframe}"] = payload
        scores.append(report.quality_score)
        if timeframe in required and not candles:
            critical_errors.append(f"data quality: required {timeframe} candles are unavailable")
        elif timeframe in required and report.status == "FAIL":
            critical_errors.append(f"data quality: {timeframe} candles failed validation")
        elif report.status != "PASS":
            warnings.append(f"{timeframe} candle quality is {report.status.lower()} ({report.quality_score}/100).")
        if timeframe in required:
            if integrity["insufficient_history"]:
                critical_errors.append(f"data quality: {timeframe} history has fewer than {integrity['minimum_rows']} candles")
            if integrity["duplicate_timestamps"]:
                critical_errors.append(f"data quality: {timeframe} contains duplicate candle timestamps")
            if integrity["out_of_order"]:
                critical_errors.append(f"data quality: {timeframe} candles are out of order")
            if integrity["unexpected_gap_count"]:
                critical_errors.append(f"data quality: {timeframe} contains {integrity['unexpected_gap_count']} unexpected interval gap(s)")
            if integrity["session_gap_count"]:
                warnings.append(f"{timeframe} contains {integrity['session_gap_count']} market-session gap(s), ignored for trade blocking.")
            if integrity["mixed_timezone_awareness"]:
                critical_errors.append(f"data quality: {timeframe} mixes timezone-aware and timezone-naive timestamps")

    if not market.valid_for_execution:
        critical_errors.append("data quality: market data is stale or invalid for execution")

    option_fields = ("oi_bias", "pcr")
    missing_options = [name for name in option_fields if not market.context_status.get(name, {}).get("available")]
    option_score = int((len(option_fields) - len(missing_options)) / len(option_fields) * 100)
    components["options"] = {
        "status": "PASS" if not missing_options else "FAIL",
        "quality_score": option_score,
        "missing_fields": missing_options,
        "observations": {name: market.context_status.get(name, {"available": False}) for name in option_fields},
    }
    scores.append(option_score)
    if missing_options:
        critical_errors.append(f"data quality: verified options context unavailable ({', '.join(missing_options)})")

    if htf.get("missing_required_timeframes"):
        missing = ", ".join(htf["missing_required_timeframes"])
        critical_errors.append(f"data quality: required higher timeframes unavailable ({missing})")

    critical_errors = _dedupe(critical_errors)
    warnings = _dedupe(warnings)
    score = int(sum(scores) / max(len(scores), 1))
    usable = not critical_errors
    return TradeDataQualityResult(
        quality_score=score,
        usable_for_trade=usable,
        status="PASS" if usable and score >= 80 else "WARN" if usable else "FAIL",
        critical_errors=critical_errors,
        warnings=warnings,
        components=components,
    )


def _candle_series_integrity(candles: list[dict[str, Any]], timeframe: str, minimum_rows: int = 20) -> dict[str, Any]:
    interval_seconds = {"TimeFrame.M1": 60, "TimeFrame.M5": 300, "TimeFrame.M15": 900, "TimeFrame.H1": 3600, "TimeFrame.D1": 86400}.get(timeframe, 0)
    parsed: list[datetime] = []
    awareness: set[bool] = set()
    for candle in candles:
        raw = candle.get("timestamp") or candle.get("datetime") or candle.get("time")
        if raw in {None, ""}:
            continue
        try:
            value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        awareness.add(value.tzinfo is not None and value.utcoffset() is not None)
        parsed.append(value)

    comparable = [value.timestamp() if value.tzinfo is not None else value.replace(tzinfo=timezone.utc).timestamp() for value in parsed]
    duplicate_count = len(comparable) - len(set(comparable))
    out_of_order = any(current <= previous for previous, current in zip(comparable, comparable[1:]))
    gap_limit = interval_seconds * (4 if timeframe == "TimeFrame.D1" else 1.5)
    gap_count = 0
    session_gap_count = 0
    for previous_value, current_value, previous_ts, current_ts in zip(parsed, parsed[1:], comparable, comparable[1:]):
        if not interval_seconds or current_ts - previous_ts <= gap_limit:
            continue
        if _is_market_session_gap(previous_value, current_value, interval_seconds):
            session_gap_count += 1
        else:
            gap_count += 1
    return {
        "rows": len(candles),
        "minimum_rows": minimum_rows,
        "timestamps_checked": len(parsed),
        "insufficient_history": bool(candles and len(candles) < minimum_rows),
        "duplicate_timestamps": duplicate_count,
        "out_of_order": out_of_order,
        "gap_count": gap_count,
        "unexpected_gap_count": gap_count,
        "session_gap_count": session_gap_count,
        "mixed_timezone_awareness": len(awareness) > 1,
    }


def _is_market_session_gap(previous: datetime, current: datetime, interval_seconds: int) -> bool:
    previous_local = _as_kolkata_naive(previous)
    current_local = _as_kolkata_naive(current)
    if current_local.date() != previous_local.date():
        return True
    market_close_seconds = 15 * 3600 + 30 * 60
    market_open_seconds = 9 * 3600 + 15 * 60
    previous_seconds = previous_local.hour * 3600 + previous_local.minute * 60 + previous_local.second
    current_seconds = current_local.hour * 3600 + current_local.minute * 60 + current_local.second
    return previous_seconds <= market_close_seconds <= current_seconds - interval_seconds or previous_seconds < market_open_seconds <= current_seconds


def _as_kolkata_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)


def analyze_higher_timeframe(market: MarketDataInputs) -> dict[str, Any]:
    series = {
        "TimeFrame.M1": market.candles_1m or market.candles,
        "TimeFrame.M5": market.candles_5m,
        "TimeFrame.M15": market.candles_15m,
        "TimeFrame.H1": market.candles_1h,
        "daily": market.candles_daily,
    }
    reads = {
        timeframe: analyze_trend(candles).trend_direction if candles else "UNAVAILABLE"
        for timeframe, candles in series.items()
    }
    availability = {timeframe: bool(candles) for timeframe, candles in series.items()}
    required_timeframes = ("TimeFrame.M15", "TimeFrame.H1")
    missing_required = [timeframe for timeframe in required_timeframes if not availability[timeframe]]
    h1_bias = _bias_from_direction(reads["TimeFrame.H1"])
    available_reads = [value for timeframe, value in reads.items() if availability[timeframe]]
    directional = {_bias_from_direction(value) for value in available_reads if _bias_from_direction(value) != "NEUTRAL"}
    conflict = bool(
        missing_required
        or len(directional) > 1
        or (_bias_from_direction(reads["TimeFrame.M15"]) not in {"NEUTRAL", h1_bias})
    )
    allowed_direction = "CE" if h1_bias == "BULLISH" else "PE" if h1_bias == "BEARISH" else "NONE"
    aligned = sum(1 for value in available_reads if _bias_from_direction(value) == h1_bias and h1_bias != "NEUTRAL")
    available_count = sum(availability.values())
    passed = bool(not missing_required and h1_bias in {"BULLISH", "BEARISH"} and not conflict)
    if missing_required:
        reason = f"Required higher-timeframe data unavailable: {', '.join(missing_required)}."
    elif passed:
        reason = "Available higher timeframes align."
    else:
        reason = "Available higher timeframes conflict or H1 is neutral."
    return {
        "timeframes": reads,
        "availability": availability,
        "missing_required_timeframes": missing_required,
        "primary_trend": h1_bias,
        "lower_timeframe_signal": _bias_from_direction(reads["TimeFrame.M1"]),
        "higher_timeframe_bias": h1_bias,
        "alignment_score": int(aligned / max(available_count, 1) * 100),
        "h1_bias": h1_bias,
        "allowed_direction": allowed_direction,
        "conflict": conflict,
        "passed": passed,
        "reason": reason,
    }


def analyze_market_structure(candles: list[dict[str, Any]], volume: VolumeAnalysis | None = None) -> dict[str, Any]:
    trend = analyze_trend(candles)
    swings = _swing_points(candles)
    swing_highs = swings["swing_highs"]
    swing_lows = swings["swing_lows"]
    has_hh = len(swing_highs) >= 2 and swing_highs[-1]["price"] > swing_highs[-2]["price"]
    has_hl = len(swing_lows) >= 2 and swing_lows[-1]["price"] > swing_lows[-2]["price"]
    has_lh = len(swing_highs) >= 2 and swing_highs[-1]["price"] < swing_highs[-2]["price"]
    has_ll = len(swing_lows) >= 2 and swing_lows[-1]["price"] < swing_lows[-2]["price"]
    if trend.trend_direction == "UPTREND" and (len(swing_highs) < 2 or len(swing_lows) < 2):
        has_hh = True
        has_hl = True
        has_lh = False
        has_ll = False
    if trend.trend_direction == "DOWNTREND" and (len(swing_highs) < 2 or len(swing_lows) < 2):
        has_hh = False
        has_hl = False
        has_lh = True
        has_ll = True
    bullish = has_hh and has_hl
    bearish = has_lh and has_ll
    structure_bias = "Bullish" if bullish else "Bearish" if bearish else "Neutral"
    volume_confirmed = bool(volume and volume.supports_trade)
    latest_close = _num(candles[-1].get("close")) if candles else 0.0
    previous_high = swing_highs[-2]["price"] if len(swing_highs) >= 2 else None
    previous_low = swing_lows[-2]["price"] if len(swing_lows) >= 2 else None
    bos = bool((bullish and previous_high is not None and latest_close > previous_high) or (bearish and previous_low is not None and latest_close < previous_low))
    reversal_warning = bool((trend.trend_direction == "UPTREND" and has_ll) or (trend.trend_direction == "DOWNTREND" and has_hh))
    latest_event = "Sideways"
    if bos and volume_confirmed:
        latest_event = "BOS"
    elif reversal_warning:
        latest_event = "CHoCH" if volume_confirmed else "MSS"
    elif bullish:
        latest_event = "HH_HL"
    elif bearish:
        latest_event = "LH_LL"
    strength_score = trend.trend_strength + (10 if bos and volume_confirmed else 0) - (20 if reversal_warning else 0)
    structure_score = max(0, min(100, int(strength_score)))
    structure_strength = "Strong" if strength_score >= 80 else "Medium" if strength_score >= 55 else "Weak"
    evidence = [
        *trend.supporting_evidence,
        f"Latest swing high is {'higher' if has_hh else 'lower' if has_lh else 'flat or unavailable'}.",
        f"Latest swing low is {'higher' if has_hl else 'lower' if has_ll else 'flat or unavailable'}.",
    ]
    warning = "CHoCH/MSS reversal risk: mixed structure." if reversal_warning or structure_bias == "Neutral" else ""
    return {
        "structure_bias": structure_bias,
        "structure_strength": structure_strength,
        "structure_score": structure_score,
        "score": structure_score,
        "latest_event": latest_event,
        "latest_structure_event": latest_event,
        "swing_highs": swing_highs[-5:],
        "swing_lows": swing_lows[-5:],
        "events": {
            "higher_high": has_hh,
            "higher_low": has_hl,
            "lower_high": has_lh,
            "lower_low": has_ll,
            "bos": bos,
            "choch_or_mss": reversal_warning,
        },
        "market_structure": evidence,
        "reason": "; ".join(evidence),
        "warning": warning,
    }


def _swing_points(candles: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    if len(candles) < 3:
        return {"swing_highs": [], "swing_lows": []}
    swing_highs: list[dict[str, Any]] = []
    swing_lows: list[dict[str, Any]] = []
    for index in range(1, len(candles) - 1):
        prev = candles[index - 1]
        cur = candles[index]
        nxt = candles[index + 1]
        high = _num(cur.get("high", cur.get("close")))
        low = _num(cur.get("low", cur.get("close")))
        if high >= _num(prev.get("high", prev.get("close"))) and high >= _num(nxt.get("high", nxt.get("close"))):
            swing_highs.append({"index": index, "price": round(high, 2)})
        if low <= _num(prev.get("low", prev.get("close"))) and low <= _num(nxt.get("low", nxt.get("close"))):
            swing_lows.append({"index": index, "price": round(low, 2)})
    if not swing_highs and candles:
        highs = [_num(candle.get("high", candle.get("close"))) for candle in candles]
        swing_highs = [{"index": highs.index(max(highs)), "price": round(max(highs), 2)}]
    if not swing_lows and candles:
        lows = [_num(candle.get("low", candle.get("close"))) for candle in candles]
        swing_lows = [{"index": lows.index(min(lows)), "price": round(min(lows), 2)}]
    return {"swing_highs": swing_highs, "swing_lows": swing_lows}


def analyze_key_levels(candles: list[dict[str, Any]]) -> dict[str, Any]:
    sr = analyze_support_resistance(candles)
    if not candles:
        return {"nearest_support": None, "nearest_resistance": None, "zone_strength": 0, "distance_from_zone": None}
    current = _num(candles[-1].get("close"))
    highs = [_num(candle.get("high", candle.get("close"))) for candle in candles]
    lows = [_num(candle.get("low", candle.get("close"))) for candle in candles]
    round_number = round(current / 50) * 50
    vwap = candles[-1].get("vwap")
    distance = min(abs(current - float(sr.support or current)), abs(float(sr.resistance or current) - current))
    return {
        "nearest_support": sr.support,
        "nearest_resistance": sr.resistance,
        "demand_zone": sr.support,
        "supply_zone": sr.resistance,
        "previous_day_high": round(max(highs), 2),
        "previous_day_low": round(min(lows), 2),
        "weekly_high": round(max(highs), 2),
        "weekly_low": round(min(lows), 2),
        "round_number": round_number,
        "vwap": float(vwap) if vwap is not None else None,
        "zone_strength": 80 if sr.warning is None else 45,
        "distance_from_zone": round(distance, 2),
    }


def analyze_supply_demand(candles: list[dict[str, Any]]) -> dict[str, Any]:
    levels = analyze_key_levels(candles)
    current = _num(candles[-1].get("close")) if candles else 0.0
    demand = levels.get("demand_zone")
    supply = levels.get("supply_zone")
    nearest = demand if demand is not None and (supply is None or abs(current - float(demand)) <= abs(float(supply) - current)) else supply
    distance = abs(current - float(nearest)) if nearest is not None else None
    tested = levels.get("zone_strength", 0) < 60
    warning = None
    if supply is not None and current > 0 and abs(float(supply) - current) / current < 0.003:
        warning = "CE is directly below strong supply."
    if demand is not None and current > 0 and abs(current - float(demand)) / current < 0.003:
        warning = "PE is directly above strong demand."
    return {
        "nearest_demand": demand,
        "nearest_supply": supply,
        "zone_strength": levels.get("zone_strength", 0),
        "distance_from_zone": round(float(distance), 2) if distance is not None else None,
        "fresh_zone": not tested,
        "tested_zone": tested,
        "broken_zone": False,
        "trade_location_quality": "Good" if warning is None and not tested else "Average" if warning is None else "Poor",
        "warning": warning,
    }


def analyze_fvg(candles: list[dict[str, Any]], trend: TrendAnalysis, levels: dict[str, Any]) -> dict[str, Any]:
    if len(candles) < 3:
        return {"type": "NONE", "state": "missing", "passed": False, "reason": "Need three candles for FVG."}
    c1, _c2, c3 = candles[-3], candles[-2], candles[-1]
    bullish_gap = _num(c3.get("low")) > _num(c1.get("high"))
    bearish_gap = _num(c3.get("high")) < _num(c1.get("low"))
    if bullish_gap:
        near_demand = levels.get("demand_zone") is not None
        passed = trend.trend_direction == "UPTREND" and near_demand
        return {"type": "BULLISH_FVG", "fvg_bias": "BULLISH", "state": "unfilled", "fvg_status": "UNFILLED", "fvg_zone": [round(_num(c1.get("high")), 2), round(_num(c3.get("low")), 2)], "confidence_impact": 5 if passed else 0, "mitigated": False, "passed": passed, "reason": "Bullish FVG near demand zone."}
    if bearish_gap:
        near_supply = levels.get("supply_zone") is not None
        passed = trend.trend_direction == "DOWNTREND" and near_supply
        return {"type": "BEARISH_FVG", "fvg_bias": "BEARISH", "state": "unfilled", "fvg_status": "UNFILLED", "fvg_zone": [round(_num(c3.get("high")), 2), round(_num(c1.get("low")), 2)], "confidence_impact": 5 if passed else 0, "mitigated": False, "passed": passed, "reason": "Bearish FVG near supply zone."}
    return {"type": "NONE", "fvg_bias": "NEUTRAL", "state": "filled_or_absent", "fvg_status": "FILLED_OR_ABSENT", "fvg_zone": None, "confidence_impact": 0, "mitigated": True, "passed": True, "reason": "No active FVG filter."}


def analyze_liquidity(candles: list[dict[str, Any]], sr: SupportResistanceAnalysis) -> dict[str, Any]:
    if len(candles) < 3 or sr.support is None or sr.resistance is None:
        return {"liquidity_event": "NONE", "liquidity_bias": "NEUTRAL", "confirmation_status": "MISSING_DATA", "reason": "Need levels and candles.", "warning": None, "passed": False}
    latest = candles[-1]
    close = _num(latest.get("close"))
    low = _num(latest.get("low", close))
    high = _num(latest.get("high", close))
    support = float(sr.support)
    resistance = float(sr.resistance)
    if low < support and close > support:
        return {"liquidity_event": "LIQUIDITY_SWEEP_BELOW_SUPPORT", "liquidity_bias": "BULLISH", "confirmation_status": "CONFIRMED", "reason": "Bullish liquidity sweep below support recovered.", "warning": None, "passed": True}
    if high > resistance and close < resistance:
        return {"liquidity_event": "LIQUIDITY_SWEEP_ABOVE_RESISTANCE", "liquidity_bias": "BEARISH", "confirmation_status": "CONFIRMED", "reason": "Bearish liquidity sweep above resistance rejected.", "warning": None, "passed": True}
    return {"liquidity_event": "NONE", "liquidity_bias": "NEUTRAL", "confirmation_status": "WAIT", "reason": "No confirmed liquidity sweep.", "warning": "Fresh sweep absent; wait for confirmation.", "passed": True}


def analyze_price_action(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < 2:
        return {"pattern": "NONE", "direction": "NEUTRAL", "confirmed": False, "reason": "Need two candles for price action."}
    prev, cur = candles[-2], candles[-1]
    po, pc = _num(prev.get("open")), _num(prev.get("close"))
    co, cc = _num(cur.get("open")), _num(cur.get("close"))
    high, low = _num(cur.get("high", cc)), _num(cur.get("low", cc))
    body = abs(cc - co)
    candle_range = max(high - low, 0.01)
    upper_wick = high - max(co, cc)
    lower_wick = min(co, cc) - low
    if cc > co and co <= pc and cc >= po:
        return {"pattern": "BULLISH_ENGULFING", "pattern_bias": "BULLISH", "pattern_strength": 85, "direction": "BULLISH", "confirmed": True, "confirmation": True, "reason": "Bullish engulfing confirms buyers."}
    if cc < co and co >= pc and cc <= po:
        return {"pattern": "BEARISH_ENGULFING", "pattern_bias": "BEARISH", "pattern_strength": 85, "direction": "BEARISH", "confirmed": True, "confirmation": True, "reason": "Bearish engulfing confirms sellers."}
    if body / candle_range >= 0.15 and lower_wick > body * 2 and cc >= co:
        return {"pattern": "HAMMER", "pattern_bias": "BULLISH", "pattern_strength": 70, "direction": "BULLISH", "confirmed": True, "confirmation": True, "reason": "Hammer shows lower-level rejection."}
    if body / candle_range >= 0.15 and upper_wick > body * 2 and cc <= co:
        return {"pattern": "SHOOTING_STAR", "pattern_bias": "BEARISH", "pattern_strength": 70, "direction": "BEARISH", "confirmed": True, "confirmation": True, "reason": "Shooting star shows upper-level rejection."}
    if body / candle_range >= 0.65:
        direction = "BULLISH" if cc > co else "BEARISH"
        return {"pattern": "STRONG_REJECTION_CANDLE", "pattern_bias": direction, "pattern_strength": 65, "direction": direction, "confirmed": True, "confirmation": True, "reason": "Strong rejection candle confirms direction."}
    pattern = "DOJI" if body / candle_range < 0.1 else "INSIDE_BAR" if high <= _num(prev.get("high", pc)) and low >= _num(prev.get("low", pc)) else "NONE"
    return {"pattern": pattern, "pattern_bias": "NEUTRAL", "pattern_strength": 20, "direction": "NEUTRAL", "confirmed": False, "confirmation": False, "reason": "No price action confirmation."}


def analyze_market_regime(market: MarketDataInputs, volume: VolumeAnalysis, trend: TrendAnalysis | None = None) -> dict[str, Any]:
    warning = None
    regime = "Trending" if not trend or trend.trend_direction != "SIDEWAYS" else "Range"
    regime_risk = "Low"
    allowed_strategy_type = "breakout_or_pullback" if regime == "Trending" else "range_or_reversal"
    confidence_impact = 5
    allowed_strategies = ["breakout", "pullback", "trend", "momentum", "vwap"] if regime == "Trending" else ["range", "reversal", "vwap"]
    blocked_strategies = ["range"] if regime == "Trending" else ["breakout", "momentum"]
    regime_strength = "Strong" if trend and trend.trend_strength >= 80 else "Medium" if trend and trend.trend_strength >= 55 else "Weak"
    if not volume.supports_trade:
        regime = "Low Volatility"
        regime_risk = "Medium"
        allowed_strategy_type = "wait"
        allowed_strategies = ["vwap"]
        blocked_strategies = ["breakout", "momentum", "opening_range"]
        regime_strength = "Weak"
        confidence_impact = -5
        warning = "Low volume reduces confidence."
    if market.expiry_day:
        regime = "Expiry Day"
        regime_risk = "High"
        allowed_strategies = ["vwap", "range"]
        blocked_strategies = ["breakout", "momentum", "opening_range"]
        confidence_impact = -8
        warning = "Expiry day increases option decay risk."
    if abs(float(market.gap_pct or 0)) >= 1.0:
        regime = "Gap Up" if market.gap_pct > 0 else "Gap Down"
        regime_risk = "High"
        allowed_strategy_type = "retest_only"
        allowed_strategies = ["pullback", "vwap"]
        blocked_strategies = ["breakout", "momentum", "opening_range"]
        confidence_impact = -10
        warning = "Big gap needs retest before entry."
    if market.india_vix is not None and market.india_vix >= 22:
        regime = "Volatile"
        regime_risk = "High"
        allowed_strategies = ["vwap", "range"]
        blocked_strategies = ["breakout", "momentum", "opening_range"]
        confidence_impact = -10
        warning = "Volatile market reduces position size."
    if market.news_driven:
        regime = "News Driven"
        regime_risk = "High"
        allowed_strategies = ["vwap"]
        blocked_strategies = ["breakout", "momentum", "opening_range", "range"]
        confidence_impact = -12
        warning = "News-driven move requires confirmation after volatility settles."
    if market.holiday_effect:
        regime = "Holiday Effect"
        regime_risk = "Medium"
        allowed_strategies = ["vwap", "range"]
        blocked_strategies = ["breakout", "momentum"]
        confidence_impact = -6
        warning = "Holiday session can reduce liquidity and follow-through."
    return {
        "market_regime": regime,
        "regime": regime,
        "regime_strength": regime_strength,
        "regime_risk": regime_risk,
        "allowed_strategy_type": allowed_strategy_type,
        "allowed_strategies": allowed_strategies,
        "blocked_strategies": blocked_strategies,
        "confidence_impact": confidence_impact,
        "warning": warning,
        "reason": warning or f"{regime} regime detected from trend, volume, VIX, gap, expiry, news, and holiday inputs.",
        "passed": regime_risk != "High",
    }


def _strategy_selection_engine(
    regime: dict[str, Any],
    structure: dict[str, Any],
    price_action: dict[str, Any],
    volume: VolumeAnalysis,
    risk: RiskRewardAnalysis,
    confluence: dict[str, Any],
    registry: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    registry_rows = registry or []
    candidates = [
        row for row in registry_rows
        if bool(row.get("enabled", True)) and int(row.get("rollout_pct") or 0) > 0
    ]
    if not candidates:
        candidates = [{"name": "none", "version": "0.0.0", "supported_regimes": [], "enabled": False, "rollout_pct": 0}]
    allowed = set(regime.get("allowed_strategies") or [])
    blocked = set(regime.get("blocked_strategies") or [])
    current_regime = str(regime.get("market_regime") or regime.get("regime") or "Unknown")
    base = int(confluence.get("confluence_score") or 0)
    scorecard: list[dict[str, Any]] = []
    for metadata in candidates:
        strategy = str(metadata.get("name") or "unknown")
        version = str(metadata.get("version") or "0.0.0")
        supported_regimes = [str(item) for item in (metadata.get("supported_regimes") or ["Any"])]
        regime_match = "Any" in supported_regimes or current_regime in supported_regimes
        score = base
        reasons: list[str] = []
        if not regime_match:
            score -= 40
            reasons.append(f"Registry does not support {current_regime} regime.")
        if strategy in allowed:
            score += 15
            reasons.append("Exact strategy is allowed by market regime.")
        elif _strategy_family(strategy) in allowed:
            score += 12
            reasons.append("Allowed by market regime.")
        if strategy in blocked or _strategy_family(strategy) in blocked:
            score -= 35
            reasons.append("Blocked by market regime.")
        if _strategy_family(strategy) in {"breakout", "momentum", "opening_range", "trend"} and volume.supports_trade:
            score += 8
            reasons.append("Volume supports directional continuation.")
        if _strategy_family(strategy) in {"pullback", "vwap", "supply_demand"} and risk.allowed:
            score += 6
            reasons.append("Risk/reward supports controlled entry.")
        if _strategy_family(strategy) == "range" and structure.get("structure_bias") == "Neutral":
            score += 10
            reasons.append("Sideways structure favors range logic.")
        if _strategy_family(strategy) in {"trend", "breakout"} and structure.get("structure_bias") in {"Bullish", "Bearish"}:
            score += 10
            reasons.append("Directional structure favors trend logic.")
        if _strategy_family(strategy) == "reversal" and structure.get("events", {}).get("choch_or_mss"):
            score += 10
            reasons.append("CHoCH/MSS supports reversal watch.")
        if price_action.get("confirmed"):
            score += 5
            reasons.append("Price action confirms setup.")
        rank_score = score
        score = max(0, min(100, score))
        scorecard.append(
            {
                "strategy": strategy,
                "version": version,
                "score": score,
                "rank_score": rank_score,
                "valid": regime_match and strategy not in blocked and _strategy_family(strategy) not in blocked and score >= 60,
                "reasons": reasons or ["No edge over current best setup."],
                "registry": {
                    "enabled": bool(metadata.get("enabled", True)),
                    "rollout_pct": int(metadata.get("rollout_pct") or 0),
                    "supported_regimes": supported_regimes,
                },
            }
        )
    ranked = sorted(scorecard, key=lambda item: (item["rank_score"], item["score"]), reverse=True)
    best = next((item for item in ranked if item["valid"]), ranked[0] if ranked else {"strategy": "none", "score": 0, "valid": False, "reasons": ["No strategy evaluated."]})
    return {
        "selected_strategy": best["strategy"] if best.get("valid") else "none",
        "strategy_version": best.get("version", "0.0.0") if best.get("valid") else "0.0.0",
        "strategy_score": best["score"],
        "selected_score": best["score"],
        "scorecard": ranked,
        "rejected_strategies": [
            {"strategy": item["strategy"], "version": item.get("version", "0.0.0"), "score": item["score"], "why_lost": item["reasons"]}
            for item in ranked
            if item["strategy"] != best.get("strategy")
        ],
        "reason": "; ".join(best.get("reasons") or []),
        "reason_selected": "; ".join(best.get("reasons") or []),
        "why_others_rejected": [
            {"strategy": item["strategy"], "why": item["reasons"]}
            for item in ranked
            if item["strategy"] != best.get("strategy")
        ],
    }


def _strategy_family(strategy: str) -> str:
    normalized = str(strategy or "").strip().lower()
    if normalized in {"mtf", "mtfa", "btst"}:
        return "trend"
    if normalized in {"amd", "supply_demand"}:
        return "supply_demand"
    if normalized in {"mean_reversion", "cbt", "crt_tbs"}:
        return "range"
    return normalized


def _probability_engine(
    confluence: dict[str, Any],
    regime: dict[str, Any],
    options_flow: dict[str, Any],
    institutional: dict[str, Any],
    risk: RiskRewardAnalysis,
) -> dict[str, Any]:
    score = float(confluence.get("confluence_score") or 0)
    score += float(regime.get("confidence_impact") or 0)
    score += 5 if options_flow.get("passed") else -8
    score += (float(institutional.get("institutional_score") or 0) - 50) * 0.15
    score += 4 if risk.allowed else -15
    readiness = int(max(0, min(100, round(score))))
    confidence = int(max(0, min(100, round((readiness + float(confluence.get("confluence_score") or 0)) / 2))))
    evidence = [
        f"Confluence score {confluence.get('confluence_score', 0)}.",
        f"Market regime {regime.get('market_regime', 'Unknown')}.",
        "Options flow supports the setup." if options_flow.get("passed") else "Options flow does not confirm.",
        f"Institutional score {institutional.get('institutional_score', 0)}.",
        "Risk/reward passes." if risk.allowed else "Risk/reward blocks or weakens confidence.",
    ]
    penalties = []
    if regime.get("regime_risk") == "High":
        penalties.append("High-risk market regime.")
    if not options_flow.get("passed"):
        penalties.append("Options flow not aligned.")
    if not risk.allowed:
        penalties.append("Risk validation failed.")
    return {
        "metric_type": "heuristic_decision_readiness",
        "readiness_score": readiness,
        "meaning": "Deterministic setup readiness; not probability of profit or expected return.",
        "not_probability_of_profit": True,
        "legacy_fields": {"probability_score": "deprecated; use readiness_score"},
        "probability_score": readiness,
        "confidence_score": confidence,
        "confidence_label": "High" if confidence >= 85 else "Medium" if confidence >= 70 else "Low" if confidence >= 55 else "Blocked",
        "evidence": evidence,
        "penalties": penalties,
        "explanation": f"Decision readiness {readiness}/100 and confidence {confidence}/100 from deterministic evidence.",
        "inputs": {
            "confluence_score": confluence.get("confluence_score"),
            "market_regime": regime.get("market_regime"),
            "options_passed": options_flow.get("passed"),
            "institutional_score": institutional.get("institutional_score"),
            "risk_reward_allowed": risk.allowed,
        },
        "reason": f"Readiness {readiness}/100 from confluence, regime, options, institutional context, and risk; not a profit forecast.",
    }


def analyze_options_flow(market: MarketDataInputs) -> dict[str, Any]:
    bias = "NEUTRAL"
    reasons: list[str] = []
    if market.pcr is not None:
        if market.pcr >= 1.05:
            bias = "BULLISH"
            reasons.append("PCR supports bulls.")
        elif market.pcr <= 0.95:
            bias = "BEARISH"
            reasons.append("PCR supports bears.")
    if market.put_oi and market.call_oi:
        if market.put_oi > market.call_oi:
            bias = "BULLISH"
            reasons.append("Put OI is stronger than Call OI.")
        elif market.call_oi > market.put_oi:
            bias = "BEARISH"
            reasons.append("Call OI is stronger than Put OI.")
    buildup = str(market.oi_change or "").strip().upper()
    if buildup:
        reasons.append(f"OI build up: {buildup}.")
    strength = 80 if len(reasons) >= 2 else 55 if reasons else 20
    return {"bias": bias, "options_bias": bias, "options_strength": strength, "support_from_put_oi": market.put_oi, "resistance_from_call_oi": market.call_oi, "passed": bias != "NEUTRAL", "pcr": market.pcr, "pcr_trend": None, "call_oi": market.call_oi, "put_oi": market.put_oi, "oi_change": market.oi_change, "max_pain": market.max_pain, "iv": market.iv, "iv_trend": None, "reason": " ".join(reasons) or "Options flow is neutral.", "warning": None if bias != "NEUTRAL" else "Conflicting/neutral OI reduces confidence."}


def analyze_institutional_filter(market: MarketDataInputs) -> dict[str, Any]:
    votes: list[str] = []
    if market.fii_cash is not None:
        votes.append("BULLISH" if market.fii_cash > 0 else "BEARISH")
    if market.dii_cash is not None:
        votes.append("BULLISH" if market.dii_cash > 0 else "BEARISH")
    if market.fii_futures is not None:
        votes.append("BULLISH" if market.fii_futures > 0 else "BEARISH")
    for value in (market.gift_nifty_bias, market.usdinr_bias, market.crude_bias, market.global_markets_bias):
        normalized = _normalize_bias(value)
        if normalized:
            votes.append(normalized)
    bullish = votes.count("BULLISH")
    bearish = votes.count("BEARISH")
    bias = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
    vix_ok = market.india_vix is None or market.india_vix < 22
    supporting = [vote for vote in votes if vote == bias and bias != "NEUTRAL"]
    opposing = [vote for vote in votes if vote != bias and vote != "NEUTRAL"]
    score = max(0, min(100, 50 + (bullish - bearish) * 15 if bias == "BULLISH" else 50 + (bearish - bullish) * 15 if bias == "BEARISH" else 40))
    if not vix_ok:
        score = min(score, 35)
    return {"bias": bias, "institutional_bias": bias, "institutional_score": score, "supporting_factors": supporting, "opposing_factors": opposing, "passed": vix_ok and bias != "NEUTRAL", "vix_ok": vix_ok, "india_vix": market.india_vix, "reason": "Institutional context supports direction." if bias != "NEUTRAL" and vix_ok else "Institutional context is neutral or volatility is elevated.", "warning": None if vix_ok else "VIX spike can block trades."}


def analyze_discipline(market: MarketDataInputs, trend: TrendAnalysis, sr: SupportResistanceAnalysis, price_action: dict[str, Any], ema: EMAAnalysis) -> dict[str, Any]:
    blocks: list[str] = []
    if trend.trend_direction == "SIDEWAYS":
        blocks.append("Trading during sideways market.")
    if sr.warning:
        blocks.append("Late entry / chasing candle.")
    if abs(float(market.gap_pct or 0.0)) >= 1.0:
        blocks.append("Trading after big gap.")
    if market.trades_today >= market.max_trades_per_day:
        blocks.append("Over trading.")
    if market.consecutive_losses >= market.max_consecutive_losses:
        blocks.append("Revenge trading risk after consecutive losses.")
    if market.duplicate_signal:
        blocks.append("Duplicate signal.")
    if not price_action.get("confirmed"):
        blocks.append("No price action confirmation.")
    warnings = ["Reduce size in elevated-risk conditions."] if market.india_vix is not None and market.india_vix >= 18 else []
    return {"passed": not blocks, "discipline_passed": not blocks, "blocked_reasons": blocks, "block_reasons": blocks, "warnings": warnings, "suggested_action": "Wait for clean retest." if blocks else "Proceed only if execution price stays inside entry zone.", "reason": "Discipline checks passed." if not blocks else blocks[0]}


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


def _high_probability_blockers(
    htf: dict[str, Any],
    price_action: dict[str, Any],
    discipline: dict[str, Any],
    options_flow: dict[str, Any],
    institutional: dict[str, Any],
    regime: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not htf["passed"]:
        blockers.append("higher timeframes conflict")
    if not price_action["confirmed"]:
        blockers.append("no price action confirmation")
    if not discipline["passed"]:
        blockers.extend(discipline["blocked_reasons"])
    if not options_flow["passed"]:
        blockers.append("options flow is neutral")
    if not institutional["passed"]:
        blockers.append("institutional filter is neutral or risky")
    if not regime["passed"]:
        blockers.append(regime.get("warning") or "market regime is risky")
    return _dedupe(blockers)


def _confluence_engine(
    trend: TrendAnalysis,
    htf: dict[str, Any],
    supply_demand: dict[str, Any],
    fvg: dict[str, Any],
    liquidity: dict[str, Any],
    price_action: dict[str, Any],
    volume: VolumeAnalysis,
    options_flow: dict[str, Any],
    institutional: dict[str, Any],
    risk: RiskRewardAnalysis,
    discipline: dict[str, Any],
) -> dict[str, Any]:
    weights = {
        "multi_timeframe_alignment": 15,
        "market_structure": 15,
        "supply_demand_or_support_resistance": 10,
        "fvg": 5,
        "liquidity_event": 5,
        "price_action": 10,
        "volume_confirmation": 10,
        "options_flow": 10,
        "institutional_score": 10,
        "risk_management": 10,
        "discipline_fomo": 10,
    }
    breakdown = {
        "multi_timeframe_alignment": weights["multi_timeframe_alignment"] if htf["passed"] else 0,
        "market_structure": weights["market_structure"] if trend.trend_direction != "SIDEWAYS" else 0,
        "supply_demand_or_support_resistance": weights["supply_demand_or_support_resistance"] if supply_demand["trade_location_quality"] != "Poor" else 0,
        "fvg": weights["fvg"] if fvg["passed"] else 0,
        "liquidity_event": weights["liquidity_event"] if liquidity["passed"] else 0,
        "price_action_confirmation": weights["price_action"] if price_action["confirmed"] else 0,
        "volume_confirmation": weights["volume_confirmation"] if volume.supports_trade else 0,
        "options_flow": weights["options_flow"] if options_flow["passed"] else 0,
        "institutional_score": weights["institutional_score"] if institutional["passed"] else 0,
        "risk_management": weights["risk_management"] if risk.allowed else 0,
        "discipline_fomo": weights["discipline_fomo"] if discipline["discipline_passed"] else 0,
    }
    raw_score = sum(breakdown.values())
    score = int(round(raw_score / max(sum(weights.values()), 1) * 100))
    hard_blocks = [
        label
        for label, value in (
            ("HTF conflict", not htf["passed"]),
            ("No price action confirmation", not price_action["confirmed"]),
            ("Poor RR", not risk.allowed),
            ("Discipline/FOMO block", not discipline["discipline_passed"]),
        )
        if value
    ]
    failed = [key for key, value in breakdown.items() if value == 0]
    passed = [key for key, value in breakdown.items() if value > 0]
    quality = _trade_quality(score, hard_blocks)
    return {
        "confluence_score": score,
        "raw_score": raw_score,
        "max_raw_score": sum(weights.values()),
        "trade_quality": quality,
        "passed_factors": passed,
        "failed_factors": failed,
        "supporting_factors": passed,
        "opposing_factors": failed,
        "hard_blocks": hard_blocks,
        "weights": weights,
        "breakdown": breakdown,
    }


def _trade_quality(score: int, hard_blocks: list[str]) -> str:
    if hard_blocks:
        return "Skip"
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Average"
    return "Poor"


def _trade_confidence_contract(market: MarketDataInputs, confluence: dict[str, Any]) -> dict[str, Any]:
    candles = market.candles_1m or market.candles
    candle = candles[-1] if candles else {}
    candle_timestamp = candle.get("timestamp") or candle.get("datetime") or candle.get("time")
    evaluated_at = datetime.now(timezone.utc).isoformat()
    weight_aliases = {"price_action_confirmation": "price_action"}
    factors = []
    for name, contribution in confluence.get("breakdown", {}).items():
        weight = int(confluence.get("weights", {}).get(weight_aliases.get(name, name), 0))
        if name == "options_flow":
            observations = [market.context_status.get("oi_bias", {}), market.context_status.get("pcr", {})]
            available = all(item.get("available") for item in observations)
            source = ", ".join(sorted({str(item.get("source")) for item in observations if item.get("source")})) or "unavailable"
            timestamp = next((item.get("timestamp") for item in observations if item.get("timestamp")), None)
        elif name in {"risk_management", "discipline_fomo"}:
            available = True
            source = "risk-engine" if name == "risk_management" else "discipline-engine"
            timestamp = evaluated_at
        else:
            available = bool(candles)
            source = "stored-live-cache" if available else "unavailable"
            timestamp = candle_timestamp
        factors.append({
            "name": name,
            "value": int(contribution),
            "direction": "SUPPORTING" if contribution > 0 else "OPPOSING",
            "weight": weight,
            "contribution": int(contribution),
            "source": source,
            "timestamp": timestamp,
            "available": available,
        })
    score = int(confluence.get("confluence_score") or 0)
    return {
        "score": score,
        "label": "READY" if score >= 70 and not confluence.get("hard_blocks") else "CAUTION" if score >= 55 else "BLOCKED",
        "meaning": "Decision readiness based on verified confluence; not probability of profit.",
        "formula": "sum(factor contributions) / sum(factor weights) * 100",
        "factors": factors,
    }


def _final_decision_payload(
    market: MarketDataInputs,
    checklist_score: int,
    blockers: list[str],
    checklist: dict[str, Any],
    market_bias: str,
    risk_reward: RiskRewardAnalysis,
    sr: SupportResistanceAnalysis,
    confluence: dict[str, Any],
    strategy_selection: dict[str, Any],
    probability: dict[str, Any],
) -> dict[str, Any]:
    system_status = "CLOSED" if not market.market_live else "STALE" if not market.valid_for_execution else "DEGRADED" if float(market.feed_delay_seconds or 0) > 10 else "LIVE"
    bullish = market_bias == "BULLISH"
    bearish = market_bias == "BEARISH"
    no_trade = bool(blockers) or confluence["trade_quality"] in {"Poor", "Skip"} or checklist_score < 55
    trade_decision = "No Trade" if no_trade else "Buy CE" if bullish else "Buy PE" if bearish else "No Trade"
    normalized_bias = "Bullish" if bullish else "Bearish" if bearish else "Neutral"
    explanation = []
    if trade_decision == "No Trade":
        explanation.append(f"No Trade because {blockers[0]}" if blockers else "No Trade because confluence is not strong enough.")
    else:
        explanation.append(f"{trade_decision}: confluence score {confluence['confluence_score']}/100 with {confluence['trade_quality']} quality.")
    no_trade_intelligence = _no_trade_intelligence(trade_decision, blockers, confluence, checklist, risk_reward, market)
    explainability = _explainability_layer(trade_decision, normalized_bias, checklist, confluence, no_trade_intelligence)
    return {
        "market_bias": normalized_bias,
        "trade_decision": trade_decision,
        "selected_strategy": strategy_selection.get("selected_strategy", "none"),
        "strategy_version": strategy_selection.get("strategy_version", "0.0.0"),
        "strategy": strategy_selection.get("selected_strategy", "none"),
        "trade_quality": confluence["trade_quality"],
        "confidence_score": probability["confidence_score"],
        "probability_score": probability["probability_score"],
        "confidence_label": probability["confidence_label"],
        "confluence_score": confluence["confluence_score"],
        "entry_zone": sr.entry_zone,
        "stop_loss": risk_reward.stop_loss,
        "target": risk_reward.target,
        "risk_reward_ratio": risk_reward.risk_reward_ratio if risk_reward.risk_reward_ratio > 0 else None,
        "position_size": risk_reward.position_size if risk_reward.position_size > 0 else None,
        "risk_level": "High" if blockers else "Low" if confluence["confluence_score"] >= 85 else "Medium",
        "explanation": explanation,
        "supporting_factors": checklist["passed"],
        "opposing_factors": checklist["failed"],
        "strategy_selection": strategy_selection,
        "probability_engine": probability,
        "block_reasons": blockers,
        "no_trade_intelligence": no_trade_intelligence,
        "explainability": explainability,
        "invalidation_level": sr.invalidation_level,
        "system_status": system_status,
    }


def _no_trade_intelligence(
    trade_decision: str,
    blockers: list[str],
    confluence: dict[str, Any],
    checklist: dict[str, Any],
    risk_reward: RiskRewardAnalysis,
    market: MarketDataInputs,
) -> dict[str, Any]:
    reasons = list(blockers)
    if confluence.get("trade_quality") in {"Poor", "Skip"}:
        reasons.extend(confluence.get("hard_blocks") or ["Trade quality is not acceptable."])
    if confluence.get("confluence_score", 0) < 70:
        reasons.append("Confluence score is below the paper-trade threshold.")
    if risk_reward.risk_reward_ratio < 1.5:
        reasons.append("Risk/reward is below 1.5.")
    if not market.valid_for_execution:
        reasons.append("Market data is stale.")
    primary = _dedupe(reasons)
    return {
        "active": trade_decision == "No Trade",
        "trade_decision": "No Trade",
        "primary_reason": primary[0] if primary else "",
        "block_reasons": primary,
        "reason_details": [_no_trade_reason_detail(reason) for reason in primary],
        "missing_confirmations": list(confluence.get("failed_factors") or []),
        "suggested_action": "Wait. Do not enter until the listed confirmations appear." if primary else "Wait for a clean pullback inside the entry zone.",
        "next_review_condition": _next_review_condition(primary, checklist, risk_reward),
        "wait_for": _wait_for(checklist, risk_reward),
        "policy": "Prefer missing a trade over taking a poor NIFTY options trade.",
    }


def _no_trade_reason_detail(reason: str) -> dict[str, str]:
    normalized = reason.lower()
    mappings = (
        (("stale", "fresh", "data quality", "timeframe", "provider", "unavailable"), "DATA_NOT_TRUSTED", "data", "critical", "Wait for complete, verified, fresh market data."),
        (("risk/reward", "risk reward", "rr "), "RISK_REWARD_INSUFFICIENT", "risk", "high", "Wait for an entry that provides at least the configured minimum risk/reward."),
        (("risk engine", "daily loss", "consecutive losses", "over trading", "revenge"), "RISK_LIMIT_ACTIVE", "risk", "critical", "Do not trade until the active risk control has cleared."),
        (("higher timeframe", "TimeFrame.M15", "TimeFrame.H1"), "TIMEFRAME_CONFIRMATION_MISSING", "confirmation", "high", "Wait for the required higher timeframes to align."),
        (("price action", "rejection", "engulfing"), "PRICE_CONFIRMATION_MISSING", "confirmation", "high", "Wait for a confirmed price-action trigger."),
        (("volume",), "VOLUME_CONFIRMATION_MISSING", "confirmation", "medium", "Wait for volume to confirm the move."),
        (("confluence", "trade quality", "checklist"), "CONFLUENCE_INSUFFICIENT", "quality", "high", "Wait until the minimum confluence and trade-quality thresholds pass."),
        (("duplicate",), "DUPLICATE_SIGNAL", "discipline", "high", "Ignore the duplicate setup and wait for a new qualified signal."),
        (("late entry", "chasing"), "ENTRY_TOO_LATE", "discipline", "high", "Wait for a clean pullback rather than chasing price."),
        (("gap",), "OPENING_GAP_RISK", "market", "high", "Wait for the gap structure and volatility to stabilize."),
    )
    for keywords, code, category, severity, remediation in mappings:
        if any(keyword in normalized for keyword in keywords):
            return {"code": code, "category": category, "severity": severity, "message": reason, "remediation": remediation}
    return {
        "code": "SETUP_NOT_QUALIFIED",
        "category": "quality",
        "severity": "medium",
        "message": reason,
        "remediation": "Wait for the failed confirmation to pass before reviewing the setup again.",
    }


def _next_review_condition(reasons: list[str], checklist: dict[str, Any], risk_reward: RiskRewardAnalysis) -> str:
    reason_text = " ".join(reasons).lower()
    if "higher timeframe" in reason_text:
        return "Review again when 15m and 1h trend align."
    if "price action" in reason_text or not (checklist.get("price_action") or {}).get("confirmed"):
        return "Review after a confirmed rejection or engulfing candle."
    if "risk/reward" in reason_text or not risk_reward.allowed:
        return "Review when RR is at least 1:1.5 from the entry zone."
    if "stale" in reason_text:
        return "Review when market data is fresh again."
    return "Review on the next clean pullback or breakout with volume."


def _wait_for(checklist: dict[str, Any], risk_reward: RiskRewardAnalysis) -> list[str]:
    wait_for: list[str] = []
    if not (checklist.get("htf") or {}).get("passed"):
        wait_for.append("Higher timeframe alignment.")
    if not (checklist.get("price_action") or {}).get("confirmed"):
        wait_for.append("A confirmed rejection or engulfing candle.")
    if not risk_reward.allowed:
        wait_for.append("Risk/reward of at least 1:1.5.")
    if not (checklist.get("options_flow") or {}).get("passed"):
        wait_for.append("Options flow supporting CE or PE direction.")
    if not wait_for:
        wait_for.append("A clean pullback inside the entry zone.")
    return wait_for


def _explainability_layer(
    trade_decision: str,
    market_bias: str,
    checklist: dict[str, Any],
    confluence: dict[str, Any],
    no_trade: dict[str, Any],
) -> dict[str, Any]:
    market_structure = checklist.get("market_structure") or {}
    htf = checklist.get("htf") or {}
    supply_demand = checklist.get("supply_demand") or {}
    price_action = checklist.get("price_action") or {}
    options_flow = checklist.get("options_flow") or {}
    rr = checklist.get("risk_reward") or {}
    if trade_decision == "No Trade":
        plain_english = f"No Trade because {no_trade.get('primary_reason') or 'the setup does not have enough confluence'}."
    else:
        direction = "CE" if trade_decision == "Buy CE" else "PE"
        plain_english = (
            f"Buy {direction} only on pullback because market bias is {market_bias.lower()}, "
            f"structure is {market_structure.get('structure_bias', 'unknown')}, "
            f"HTF direction is {htf.get('allowed_direction', 'unknown')}, "
            f"supply/demand location is {supply_demand.get('trade_location_quality', 'unknown')}, "
            f"price action is {price_action.get('pattern', 'unknown')}, "
            f"options flow is {options_flow.get('bias', 'unknown')}, "
            f"and risk/reward is 1:{rr.get('risk_reward_ratio', 0)}."
        )
    return {
        "plain_english": plain_english,
        "score_reason": f"Confluence score {confluence.get('confluence_score', 0)}/100; quality {confluence.get('trade_quality', 'Skip')}.",
        "supporting_factors": list(confluence.get("supporting_factors") or []),
        "opposing_factors": list(confluence.get("opposing_factors") or []),
        "warnings": _dedupe(list(checklist.get("warnings") or []) + list(no_trade.get("block_reasons") or [])),
    }


def _paper_trade_gate(
    market: MarketDataInputs,
    final_decision: dict[str, Any],
    risk_reward: RiskRewardAnalysis,
    discipline: dict[str, Any],
    confluence: dict[str, Any],
    risk_blocked: bool = False,
) -> dict[str, Any]:
    reasons: list[str] = []
    score = int(confluence.get("confluence_score") or 0)
    trade_quality = str(confluence.get("trade_quality") or final_decision.get("trade_quality") or "Skip")
    rr = float(risk_reward.risk_reward_ratio or 0.0)

    if score < 70:
        reasons.append("Confluence score is below 70.")
    if trade_quality not in {"Good", "Excellent"}:
        reasons.append("Trade quality is not Good or Excellent.")
    if not risk_reward.allowed or rr < 1.5:
        reasons.append("Risk/reward is below 1.5.")
    if risk_blocked:
        reasons.append("Risk engine blocked the trade.")
    if not discipline.get("discipline_passed"):
        reasons.extend(discipline.get("block_reasons") or ["Discipline engine blocked the trade."])
    if not market.valid_for_execution:
        reasons.append("Data is stale.")
    if final_decision.get("trade_decision") == "No Trade":
        reasons.extend(final_decision.get("block_reasons") or ["Final decision is No Trade."])

    return {
        "allowed": not reasons,
        "status": "Allowed" if not reasons else "Blocked",
        "reasons": _dedupe(reasons),
        "thresholds": {
            "minimum_confluence_score": 70,
            "allowed_trade_quality": ["Good", "Excellent"],
            "minimum_risk_reward": 1.5,
            "requires_risk_engine_pass": True,  # nosec B105
            "requires_discipline_engine_pass": True,  # nosec B105
            "requires_fresh_data": True,
        },
    }


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


_MARKET_CONTEXT_FIELDS = (
    "trend",
    "momentum",
    "price_action",
    "oi_bias",
    "pcr",
    "max_pain",
    "india_vix",
    "fii_dii_bias",
    "gift_nifty_bias",
    "vwap_relation",
    "liquidity",
    "call_oi",
    "put_oi",
    "iv",
    "expiry_day",
)


def _verified_market_context(
    context: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    values: dict[str, Any] = {}
    statuses: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    disallowed_sources = ("sample", "synthetic", "fallback", "mock", "environment")
    for field_name in _MARKET_CONTEXT_FIELDS:
        item = context.get(field_name)
        if not isinstance(item, dict):
            statuses[field_name] = {"available": False, "reason": "not provided"}
            continue
        source = str(item.get("source") or "").strip()
        timestamp = str(item.get("timestamp") or "").strip()
        live_suitable = item.get("live_suitable") is True
        source_allowed = bool(source) and not any(marker in source.lower() for marker in disallowed_sources)
        timestamp_valid = _context_timestamp_valid(timestamp)
        value_available = item.get("available") is True and item.get("value") is not None
        verified = bool(value_available and source_allowed and timestamp_valid and live_suitable)
        reasons: list[str] = []
        if not value_available:
            reasons.append("value unavailable")
        if not source_allowed:
            reasons.append("source is missing or non-trading-grade")
        if not timestamp_valid:
            reasons.append("timestamp is missing, invalid, or timezone-naive")
        if not live_suitable:
            reasons.append("source is not marked live-suitable")
        statuses[field_name] = {
            "available": verified,
            "source": source or "unknown",
            "timestamp": timestamp or None,
            "live_suitable": live_suitable,
            "reason": "; ".join(reasons) if reasons else "verified",
        }
        if verified:
            values[field_name] = item["value"]
        else:
            warnings.append(f"{field_name.replace('_', ' ').title()} ignored: {statuses[field_name]['reason']}.")
    if not statuses["oi_bias"]["available"] or not statuses["pcr"]["available"]:
        warnings.append("Verified options context is unavailable; options evidence cannot support a trade.")
    return values, statuses, _dedupe(warnings)


def _context_timestamp_valid(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _context_text(values: dict[str, Any], name: str) -> str | None:
    value = values.get(name)
    return str(value) if value is not None else None


def _context_number(values: dict[str, Any], name: str) -> float | None:
    value = values.get(name)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
