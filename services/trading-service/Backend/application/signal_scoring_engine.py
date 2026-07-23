from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ==========================================================
# MODELS
# ==========================================================

@dataclass
class StrategySignal:
    symbol: str
    side: str
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
    institutional: bool
    news: bool


@dataclass
class TradingDecision:
    confidence: int
    execute: bool


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
    reason: str = ""


# ==========================================================
# SIGNAL SCORING ENGINE
# ==========================================================

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

        scores["confidence"] = min(data.signal.confidence, 100) * 20 // 100

        scores["trend"] = (
            15 if data.market.trend == "Strong Trend"
            else 10 if data.market.trend == "Trend"
            else 5
        )

        scores["volume"] = (
            10 if data.market.volume == "High"
            else 5
        )

        scores["risk_reward"] = (
            15 if data.signal.risk_reward >= 2
            else 10 if data.signal.risk_reward >= 1.5
            else 5
        )

        scores["institutional"] = (
            10 if data.market.institutional else 0
        )

        scores["oi_pcr"] = (
            10 if 0.8 <= data.market.pcr <= 1.2 else 5
        )

        scores["vwap"] = (
            5 if data.market.vwap_relation == "Above" else 0
        )

        scores["atr"] = (
            5 if data.market.atr > 1 else 2
        )

        scores["spread"] = (
            5 if data.market.spread <= 0.20 else 2
        )

        scores["news"] = (
            0 if data.market.news else 5
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

        return SignalScore(
            total_score=total,
            confidence=data.signal.confidence,
            grade=grade,
            execute=total >= 80,
            reasons=[
                f"{k}: {v}"
                for k, v in scores.items()
            ],
            component_scores=scores,
        )


# ==========================================================
# RISK MANAGER
# ==========================================================

class RiskManager:

    def evaluate(
        self,
        signal: StrategySignal,
        score: SignalScore,
    ) -> RiskGateResult:

        if not score.execute:
            return RiskGateResult(False, "Low score")

        if signal.risk_reward < 1.5:
            return RiskGateResult(False, "Poor Risk Reward")

        return RiskGateResult(True)


# ==========================================================
# ORDER MANAGEMENT
# ==========================================================

class OrderManagementService:

    def submit_order(
        self,
        signal: StrategySignal,
    ) -> dict[str, Any]:

        return {
            "status": "SUCCESS",
            "symbol": signal.symbol,
            "side": signal.side,
        }


# ==========================================================
# ANALYTICS
# ==========================================================

class TradeAnalytics:

    def record(
        self,
        order: dict,
        score: SignalScore,
    ):

        print(
            f"Analytics -> {order['symbol']} "
            f"Score={score.total_score}"
        )


# ==========================================================
# FEEDBACK
# ==========================================================

class FeedbackEngine:

    def learn(
        self,
        order: dict,
        score: SignalScore,
    ):
        print(
            f"Learning from {order['symbol']}"
        )


# ==========================================================
# TRADING SERVICE
# ==========================================================

class TradingService:

    def run_strategy(
        self,
        strategy: str,
        market: MarketDataInputs,
    ) -> list[StrategySignal]:

        return [
            StrategySignal(
                symbol="NIFTY",
                side="BUY",
                confidence=92,
                risk_reward=2.4,
            )
        ]


# ==========================================================
# ORCHESTRATOR
# ==========================================================

class TradingOrchestrator:

    def __init__(self):

        self.trading_service = TradingService()
        self.scoring = SignalScoringEngine()
        self.risk = RiskManager()
        self.oms = OrderManagementService()
        self.analytics = TradeAnalytics()
        self.feedback = FeedbackEngine()

    def execute(
        self,
        strategy: str,
        market: MarketDataInputs,
        decision: TradingDecision,
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
                    decision=decision,
                    strategy_name=strategy,
                )
            )

            if not score.execute:
                continue

            gate = self.risk.evaluate(
                signal,
                score,
            )

            if not gate.allowed:
                continue

            order = self.oms.submit_order(signal)

            self.analytics.record(
                order,
                score,
            )

            self.feedback.learn(
                order,
                score,
            )

            return order

        return None