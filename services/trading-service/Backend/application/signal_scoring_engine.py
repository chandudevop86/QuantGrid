from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
# SCORING ENGINE
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

    def score(self, data: SignalScoringInput) -> SignalScore:

        scores = {}

        scores["confidence"] = min(data.signal.confidence, 100) * self.WEIGHTS["confidence"] // 100

        scores["trend"] = (
            self.WEIGHTS["trend"]
            if data.market.trend.lower() == "strong trend"
            else self.WEIGHTS["trend"] // 2
        )

        scores["volume"] = (
            self.WEIGHTS["volume"]
            if data.market.volume.lower() == "high"
            else self.WEIGHTS["volume"] // 2
        )

        rr = data.signal.risk_reward
        scores["risk_reward"] = (
            self.WEIGHTS["risk_reward"]
            if rr >= 2
            else int(rr / 2 * self.WEIGHTS["risk_reward"])
        )

        scores["institutional"] = (
            self.WEIGHTS["institutional"]
            if data.market.institutional
            else 0
        )

        scores["oi_pcr"] = (
            self.WEIGHTS["oi_pcr"]
            if 0.8 <= data.market.pcr <= 1.2
            else self.WEIGHTS["oi_pcr"] // 2
        )

        scores["vwap"] = (
            self.WEIGHTS["vwap"]
            if data.market.vwap_relation.lower() == "above"
            else 0
        )

        scores["atr"] = (
            self.WEIGHTS["atr"]
            if data.market.atr > 0
            else 0
        )

        scores["spread"] = (
            self.WEIGHTS["spread"]
            if data.market.spread < 1
            else 0
        )

        scores["news"] = (
            0
            if data.market.news
            else self.WEIGHTS["news"]
        )

        total = sum(scores.values())

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

        execute = total >= 80

        reasons = [
            f"{k}: {v}"
            for k, v in scores.items()
            if v > 0
        ]

        return SignalScore(
            total_score=total,
            confidence=data.signal.confidence,
            grade=grade,
            execute=execute,
            reasons=reasons,
            component_scores=scores,
        )


# ============================================================
# RISK MANAGER
# ============================================================

class RiskManager:

    def evaluate(self, score: SignalScore) -> RiskGateResult:

        if score.total_score < 80:
            return RiskGateResult(False, "Low score")

        return RiskGateResult(True, "Approved")


# ============================================================
# OMS
# ============================================================

class OrderManagementService:

    def submit_order(self, signal: StrategySignal) -> dict[str, Any]:

        print(
            f"Submitting {signal.action} order for {signal.symbol}"
        )

        return {
            "status": "SUCCESS",
            "symbol": signal.symbol,
            "action": signal.action,
        }


# ============================================================
# ANALYTICS
# ============================================================

class TradeAnalytics:

    def record(
        self,
        order: dict[str, Any],
        score: SignalScore,
    ) -> None:

        print(
            f"Analytics -> {order['symbol']} Score={score.total_score}"
        )


# ============================================================
# FEEDBACK
# ============================================================

class FeedbackEngine:

    def learn(
        self,
        order: dict[str, Any],
        score: SignalScore,
    ) -> None:

        print(
            f"Learning from {order['symbol']}"
        )


# ============================================================
# STRATEGY SERVICE
# ============================================================

class TradingService:

    def run_strategy(
        self,
        strategy: str,
        market: MarketDataInputs,
    ) -> list[StrategySignal]:

        return [
            StrategySignal(
                symbol="NIFTY",
                action="BUY",
                confidence=87,
                risk_reward=2.5,
            )
        ]


# ============================================================
# PIPELINE
# ============================================================

class DecisionPipelineService:

    def __init__(self):

        self.decision = TradingDecision(
            confidence=90,
            sentiment="Bullish",
        )


# ============================================================
# ORCHESTRATOR
# ============================================================

class TradingOrchestrator:

    def __init__(self):

        self.pipeline = DecisionPipelineService()
        self.trading_service = TradingService()
        self.scoring = SignalScoringEngine()
        self.risk = RiskManager()
        self.oms = OrderManagementService( broker="dhan")
        self.analytics = TradeAnalytics()
        self.feedback = FeedbackEngine()

    def execute(
        self,
        market: MarketDataInputs,
        strategy: str,
    ):

        signals = self.trading_service.run_strategy(
            strategy,
            market,
        )

        for signal in signals:

            score = self.scoring.score(
                SignalScoringInput(
                    signal=signal,
                    market=market,
                    decision=self.pipeline.decision,
                    strategy_name=strategy,
                )
            )

            if not score.execute:
                continue

            gate = self.risk.evaluate(score)

            if not gate.allowed:
                continue

            order = self.oms.submit_order(signal)

            self.analytics.record(order, score)

            self.feedback.learn(order, score)


# ============================================================
# EXAMPLE
# ============================================================

if __name__ == "__main__":

    market = MarketDataInputs(
        trend="Strong Trend",
        market_regime="Trending",
        volume="High",
        volatility="High",
        oi_bias="Bullish",
        pcr=1.0,
        vwap_relation="Above",
        atr=120,
        spread=0.4,
        news=False,
        institutional=True,
        expiry_day=False,
    )

    orchestrator = TradingOrchestrator()
    orchestrator.execute(market, "breakout")
    