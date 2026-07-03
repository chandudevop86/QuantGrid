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

    def to_dict(self) -> dict:
        return asdict(self)


class DecisionEngine:
    def decide(self, inputs: DecisionInputs) -> TradingDecision:
        if inputs.risk_blocked:
            return self._no_trade(
                inputs,
                confidence=35,
                explanation="Risk controls are blocking new trades. Protect capital.",
                status="Caution",
                entry_zone="Wait until risk limits reset",
            )

        if not inputs.market_live or not inputs.valid_for_execution:
            reason = "Market is closed." if not inputs.market_live else "Market data is not clean enough."
            if inputs.warnings:
                reason = f"{reason} {inputs.warnings[0]}"
            return self._no_trade(inputs, confidence=48, explanation=reason, status="Caution")

        bias = self._normalize_bias(inputs.market_bias)
        confidence = 78 if float(inputs.feed_delay_seconds or 0) <= 10 else 64
        if bias == "Neutral":
            return self._no_trade(
                inputs,
                confidence=confidence,
                explanation="Market data is usable, but directional edge is not strong enough yet.",
                status="Ready",
                risk_level="Medium",
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
            simple_explanation=f"Market structure favors {direction}. Options positioning supports {participants}.",
            system_status="Ready",
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
        )

    @staticmethod
    def _normalize_bias(value: str) -> Bias:
        normalized = str(value or "").strip().upper()
        if normalized == "BULLISH":
            return "Bullish"
        if normalized == "BEARISH":
            return "Bearish"
        return "Neutral"
