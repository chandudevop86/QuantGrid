from __future__ import annotations

from dataclasses import dataclass, field


# ============================================================
# MODELS
# ============================================================

@dataclass
class StrategySignal:
    symbol: str
    action: str
    confidence: int
    risk_reward: float


@dataclass
class MarketDataInputs:
    trend: str
    market_regime: str
    volume: str
    volatility: str
    oi_bias: str
    pcr: float
    vwap_relation: str
    atr: float
    spread: float
    news: bool
    institutional: bool
    expiry_day: bool


@dataclass
class TradingDecision:
    confidence: int
    sentiment: str


@dataclass
class SignalScoringInput:
    signal: StrategySignal
    market: MarketDataInputs
    decision: TradingDecision
    strategy_name: str


@dataclass
class SignalScore:
    total_score: int
    confidence: int
    grade: str
    execute: bool
    reasons: list[str] = field(default_factory=list)
    component_scores: dict[str, int] = field(default_factory=dict)


@dataclass
class RiskGateResult:
    allowed: bool
    reason: str


# ============================================================
# SIGNAL SCORING ENGINE
# ============================================================

class SignalScoringEngine:

    WEIGHTS = {
        "confidence": 20,
        "trend": 15,
        "volume": 10,
        "risk_reward": 15,
        "institutional": 10,
        "oi_pcr": 10,
        "vwap": 5,
        "atr": 5,
        "spread": 5,
        "news": 5,
    }

    def score(
        self,
        data: SignalScoringInput,
    ) -> SignalScore:

        scores: dict[str, int] = {}

        # ----------------------------------------------------
        # CONFIDENCE
        # ----------------------------------------------------

        confidence = max(
            0,
            min(
                int(data.signal.confidence),
                100,
            ),
        )

        scores["confidence"] = (
            confidence
            * self.WEIGHTS["confidence"]
            // 100
        )

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        trend = str(
            data.market.trend or ""
        ).strip().lower()

        if trend == "strong trend":
            scores["trend"] = self.WEIGHTS["trend"]
        else:
            scores["trend"] = (
                self.WEIGHTS["trend"] // 2
            )

        # ----------------------------------------------------
        # VOLUME
        # ----------------------------------------------------

        volume = str(
            data.market.volume or ""
        ).strip().lower()

        if volume == "high":
            scores["volume"] = self.WEIGHTS["volume"]
        else:
            scores["volume"] = (
                self.WEIGHTS["volume"] // 2
            )

        # ----------------------------------------------------
        # RISK / REWARD
        # ----------------------------------------------------

        rr = max(
            0.0,
            float(data.signal.risk_reward),
        )

        if rr >= 2.0:
            scores["risk_reward"] = (
                self.WEIGHTS["risk_reward"]
            )
        else:
            scores["risk_reward"] = min(
                self.WEIGHTS["risk_reward"],
                int(
                    rr / 2.0
                    * self.WEIGHTS["risk_reward"]
                ),
            )

        # ----------------------------------------------------
        # INSTITUTIONAL FLOW
        # ----------------------------------------------------

        scores["institutional"] = (
            self.WEIGHTS["institutional"]
            if bool(data.market.institutional)
            else 0
        )

        # ----------------------------------------------------
        # OI / PCR
        # ----------------------------------------------------

        pcr = float(data.market.pcr)

        scores["oi_pcr"] = (
            self.WEIGHTS["oi_pcr"]
            if 0.8 <= pcr <= 1.2
            else self.WEIGHTS["oi_pcr"] // 2
        )

        # ----------------------------------------------------
        # VWAP
        # ----------------------------------------------------

        vwap_relation = str(
            data.market.vwap_relation or ""
        ).strip().lower()

        scores["vwap"] = (
            self.WEIGHTS["vwap"]
            if vwap_relation == "above"
            else 0
        )

        # ----------------------------------------------------
        # ATR
        # ----------------------------------------------------

        scores["atr"] = (
            self.WEIGHTS["atr"]
            if float(data.market.atr) > 0
            else 0
        )

        # ----------------------------------------------------
        # SPREAD
        # ----------------------------------------------------

        scores["spread"] = (
            self.WEIGHTS["spread"]
            if float(data.market.spread) < 1
            else 0
        )

        # ----------------------------------------------------
        # NEWS
        # ----------------------------------------------------

        scores["news"] = (
            0
            if bool(data.market.news)
            else self.WEIGHTS["news"]
        )

        # ----------------------------------------------------
        # TOTAL
        # ----------------------------------------------------

        total = sum(scores.values())

        # ----------------------------------------------------
        # GRADE
        # ----------------------------------------------------

        if total >= 90:
            grade = "A+"
        elif total >= 80:
            grade = "A"
        elif total >= 70:
            grade = "B"
        elif total >= 60:
            grade = "C"
        else:
            grade = "D"

        # ----------------------------------------------------
        # EXECUTION THRESHOLD
        # ----------------------------------------------------

        execute = total >= 80

        # ----------------------------------------------------
        # EXPLAINABILITY
        # ----------------------------------------------------

        reasons = [
            f"{key}: {value}"
            for key, value in scores.items()
            if value > 0
        ]

        return SignalScore(
            total_score=total,
            confidence=confidence,
            grade=grade,
            execute=execute,
            reasons=reasons,
            component_scores=scores,
        )


# ============================================================
# RISK GATE
# ============================================================

class RiskManager:

    MIN_SCORE = 80

    def evaluate(
        self,
        score: SignalScore,
    ) -> RiskGateResult:

        if score.total_score < self.MIN_SCORE:
            return RiskGateResult(
                allowed=False,
                reason=(
                    f"Low score: "
                    f"{score.total_score} "
                    f"< {self.MIN_SCORE}"
                ),
            )

        return RiskGateResult(
            allowed=True,
            reason="Approved",
        )


# ============================================================
# ANALYTICS
# ============================================================

class TradeAnalytics:

    def record(
        self,
        order: dict,
        score: SignalScore,
    ) -> None:

        print(
            f"Analytics -> "
            f"{order.get('symbol')} "
            f"Score={score.total_score}"
        )


# ============================================================
# FEEDBACK
# ============================================================

class FeedbackEngine:

    def learn(
        self,
        order: dict,
        score: SignalScore,
    ) -> None:

        print(
            f"Learning from "
            f"{order.get('symbol')}"
        )


# ============================================================
# END
# ============================================================