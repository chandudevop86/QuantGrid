from __future__ import annotations

import os
from dataclasses import dataclass, field
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
        decision = self.decision_engine.decide(
            DecisionInputs(
                market_live=market.market_live,
                valid_for_execution=market.valid_for_execution,
                risk_blocked=risk_blocked,
                feed_delay_seconds=market.feed_delay_seconds,
                warnings=market.warnings,
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
        trend = _normalize_bias(market.trend) or self._trend_from_candles(market.candles)
        momentum = _normalize_bias(market.momentum) or self._momentum_from_candles(market.candles)
        vwap_relation = market.vwap_relation or self._vwap_relation(market.candles)
        directional_votes = [
            trend,
            momentum,
            _normalize_bias(market.price_action),
            _normalize_bias(market.oi_bias),
            _normalize_bias(market.fii_dii_bias),
            _normalize_bias(market.gift_nifty_bias),
        ]
        market_bias = _majority_bias(directional_votes)
        return {
            "market_bias": market_bias,
            "trend": trend,
            "momentum": momentum,
            "price_action": _normalize_bias(market.price_action),
            "support": market.support,
            "resistance": market.resistance,
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
