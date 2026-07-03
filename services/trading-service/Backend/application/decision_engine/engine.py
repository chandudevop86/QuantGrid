from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Bias = Literal["Bullish", "Bearish", "Neutral"]
Recommendation = Literal["Buy CE", "Buy PE", "No Trade"]


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    market_live: bool
    valid_for_execution: bool
    risk_blocked: bool
    feed_delay_seconds: int | float = 0
    warnings: list[str] = field(default_factory=list)
    market_bias: str = "NEUTRAL"
    market_trend: str | None = None
    price_action: str | None = None
    support: str = "Nearest confirmed demand zone"
    resistance: str = "Nearest confirmed supply zone"
    oi_bias: str | None = None
    pcr: float | None = None
    vix: float | None = None
    fii_dii_bias: str | None = None
    max_pain: str | None = None
    vwap_relation: str | None = None
    gift_nifty_bias: str | None = None
    expiry_day: bool = False
    confidence_threshold: int = 70


@dataclass(frozen=True, slots=True)
class TradingDecision:
    market_bias: Bias
    trade_recommendation: Recommendation
    confidence: int
    entry_zone: str
    stop_loss: str
    target: str
    risk_level: str
    support: str
    resistance: str
    simple_explanation: str
    system_status: str
    invalidation_level: str
    supporting_factors: list[str]
    opposing_factors: list[str]
    warnings: list[str]
    data_status: Literal["LIVE", "DEGRADED", "STALE", "CLOSED"]
    blocked: bool

    def to_dict(self) -> dict:
        return asdict(self)


class DecisionEngine:
    def decide(self, inputs: DecisionInputs) -> TradingDecision:
        if inputs.risk_blocked:
            data_status = self._data_status(inputs)
            return self._no_trade(
                inputs,
                confidence=35,
                explanation="Risk controls are blocking new trades. Protect capital.",
                status=data_status,
                data_status=data_status,
                entry_zone="Wait until risk limits reset",
            )

        data_status = self._data_status(inputs)
        if not inputs.market_live or not inputs.valid_for_execution:
            reason = "Market is closed." if not inputs.market_live else "Market data is not clean enough."
            if inputs.warnings:
                reason = f"{reason} {inputs.warnings[0]}"
            return self._no_trade(inputs, confidence=48, explanation=reason, status=data_status, data_status=data_status)

        bias = self._normalize_bias(inputs.market_bias)
        supporting, opposing, warnings = self._factor_ledger(inputs, bias)
        confidence = self._confidence(inputs, supporting, opposing, warnings)
        if bias == "Neutral":
            return self._no_trade(
                inputs,
                confidence=confidence,
                explanation="Market data is usable, but directional edge is not strong enough yet.",
                status=data_status,
                risk_level="Medium",
                data_status=data_status,
                supporting_factors=supporting,
                opposing_factors=opposing,
                warnings=warnings,
            )
        if confidence < int(inputs.confidence_threshold):
            return self._no_trade(
                inputs,
                confidence=confidence,
                explanation=f"{bias} setup exists, but confidence is below the {inputs.confidence_threshold}% trade threshold.",
                status=data_status,
                risk_level="Medium",
                data_status=data_status,
                supporting_factors=supporting,
                opposing_factors=opposing,
                warnings=warnings,
            )

        recommendation: Recommendation = "Buy CE" if bias == "Bullish" else "Buy PE"
        direction = "upside" if bias == "Bullish" else "downside"
        participants = "bulls" if bias == "Bullish" else "bears"
        return TradingDecision(
            market_bias=bias,
            trade_recommendation=recommendation,
            confidence=confidence,
            entry_zone="Wait for price to confirm direction",
            stop_loss="Below or above the decision zone",
            target="Next intraday support or resistance",
            risk_level="Medium",
            support=inputs.support,
            resistance=inputs.resistance,
            simple_explanation=self._explain_trade(bias, supporting, opposing),
            system_status=data_status,
            invalidation_level="Below support" if bias == "Bullish" else "Above resistance",
            supporting_factors=supporting,
            opposing_factors=opposing,
            warnings=warnings,
            data_status=data_status,
            blocked=False,
        )

    def _no_trade(
        self,
        inputs: DecisionInputs,
        *,
        confidence: int,
        explanation: str,
        status: str,
        entry_zone: str = "Wait for a clean pullback near support",
        risk_level: str = "Low",
        data_status: Literal["LIVE", "DEGRADED", "STALE", "CLOSED"] = "DEGRADED",
        supporting_factors: list[str] | None = None,
        opposing_factors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> TradingDecision:
        return TradingDecision(
            market_bias="Neutral",
            trade_recommendation="No Trade",
            confidence=confidence,
            entry_zone=entry_zone,
            stop_loss="Below the decision zone" if entry_zone != "Wait until risk limits reset" else "Not applicable",
            target="Next intraday level" if entry_zone != "Wait until risk limits reset" else "Not applicable",
            risk_level=risk_level,
            support=inputs.support,
            resistance=inputs.resistance,
            simple_explanation=explanation,
            system_status=status,
            invalidation_level="No active view",
            supporting_factors=supporting_factors or [],
            opposing_factors=opposing_factors or [],
            warnings=warnings or list(inputs.warnings),
            data_status=data_status,
            blocked=True,
        )

    @staticmethod
    def _normalize_bias(value: str) -> Bias:
        normalized = str(value or "").strip().upper()
        if normalized == "BULLISH":
            return "Bullish"
        if normalized == "BEARISH":
            return "Bearish"
        return "Neutral"

    @staticmethod
    def _data_status(inputs: DecisionInputs) -> Literal["LIVE", "DEGRADED", "STALE", "CLOSED"]:
        if not inputs.market_live:
            return "CLOSED"
        if not inputs.valid_for_execution:
            return "STALE"
        return "LIVE" if float(inputs.feed_delay_seconds or 0) <= 10 else "DEGRADED"

    def _factor_ledger(self, inputs: DecisionInputs, bias: Bias) -> tuple[list[str], list[str], list[str]]:
        supporting: list[str] = []
        opposing: list[str] = []
        warnings: list[str] = list(inputs.warnings)
        expected = bias.upper()

        for label, value in (
            ("Trend", inputs.market_trend),
            ("Price action", inputs.price_action),
            ("OI", inputs.oi_bias),
            ("FII/DII", inputs.fii_dii_bias),
            ("GIFT NIFTY", inputs.gift_nifty_bias),
        ):
            normalized = str(value or "").upper()
            if expected != "NEUTRAL" and normalized == expected:
                supporting.append(f"{label} supports {bias.lower()} bias.")
            elif normalized in {"BULLISH", "BEARISH"} and normalized != expected:
                opposing.append(f"{label} conflicts with {bias.lower()} bias.")

        if bias != "Neutral":
            supporting.insert(0, f"Primary decision model supports {bias.lower()} bias.")

        if inputs.vwap_relation:
            relation = str(inputs.vwap_relation).lower()
            if (bias == "Bullish" and "above" in relation) or (bias == "Bearish" and "below" in relation):
                supporting.append("Price is aligned with VWAP.")
            elif bias != "Neutral":
                opposing.append("VWAP does not confirm the setup.")

        if inputs.pcr is not None:
            pcr = float(inputs.pcr)
            if bias == "Bullish" and pcr >= 1.05:
                supporting.append("Options positioning supports bullish bias.")
            elif bias == "Bearish" and pcr <= 0.95:
                supporting.append("Options positioning supports bearish bias.")
            elif bias != "Neutral":
                opposing.append("Options positioning is not aligned.")

        if inputs.max_pain:
            supporting.append(f"Max Pain reference is {inputs.max_pain}.")
        if inputs.vix is not None and float(inputs.vix) >= 22:
            warnings.append("India VIX is elevated; option premiums can move sharply.")
            opposing.append("High volatility reduces signal quality.")
        if inputs.expiry_day:
            warnings.append("Expiry-day premium decay risk is elevated.")
            opposing.append("Expiry decay can hurt option buyers.")
        if float(inputs.feed_delay_seconds or 0) > 10:
            warnings.append("Market data is degraded.")
            opposing.append("Feed delay reduces confidence.")
        return supporting, opposing, warnings

    def _confidence(self, inputs: DecisionInputs, supporting: list[str], opposing: list[str], warnings: list[str]) -> int:
        score = 66 + len(supporting) * 7 - len(opposing) * 9
        if float(inputs.feed_delay_seconds or 0) > 10:
            score -= 10
        if inputs.vix is not None and float(inputs.vix) >= 22:
            score -= 12
        if inputs.expiry_day:
            score -= 8
        if str(inputs.market_trend or "").upper() == "WEAK":
            score -= 8
        score -= min(10, len(warnings) * 2)
        return max(0, min(100, int(score)))

    @staticmethod
    def _explain_trade(bias: Bias, supporting: list[str], opposing: list[str]) -> str:
        direction = "upside" if bias == "Bullish" else "downside"
        if supporting:
            first_reason = supporting[0].replace("Primary decision model", "Decision model")
        else:
            first_reason = f"Market structure favors {direction}."
        caution = f" Watch: {opposing[0]}" if opposing else ""
        return f"{first_reason} Price action favors {direction}. Invalidates if price loses the decision zone.{caution}"
