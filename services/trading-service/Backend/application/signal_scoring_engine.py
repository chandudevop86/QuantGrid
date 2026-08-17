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
# SCORING ENGINE
# ============================================================


class SignalScoringEngine:
    """
    Calculates the strategy signal quality score.

    This class is intentionally responsible only for scoring.

    It does NOT:
      - submit broker orders
      - create database orders
      - update order persistence
      - manage retries
      - send trade notifications
      - act as an OMS
    """

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

        # --------------------------------------------------------
        # Confidence
        # --------------------------------------------------------

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

        # --------------------------------------------------------
        # Trend
        # --------------------------------------------------------

        trend = str(
            data.market.trend or ""
        ).strip().lower()

        scores["trend"] = (
            self.WEIGHTS["trend"]
            if trend == "strong trend"
            else self.WEIGHTS["trend"] // 2
        )

        # --------------------------------------------------------
        # Volume
        # --------------------------------------------------------

        volume = str(
            data.market.volume or ""
        ).strip().lower()

        scores["volume"] = (
            self.WEIGHTS["volume"]
            if volume == "high"
            else self.WEIGHTS["volume"] // 2
        )

        # --------------------------------------------------------
        # Risk / Reward
        # --------------------------------------------------------

        rr = max(
            0.0,
            float(data.signal.risk_reward),
        )

        if rr >= 2:
            scores["risk_reward"] = (
                self.WEIGHTS["risk_reward"]
            )
        else:
            scores["risk_reward"] = min(
                self.WEIGHTS["risk_reward"],
                max(
                    0,
                    int(
                        rr
                        / 2
                        * self.WEIGHTS["risk_reward"]
                    ),
                ),
            )

        # --------------------------------------------------------
        # Institutional
        # --------------------------------------------------------

        scores["institutional"] = (
            self.WEIGHTS["institutional"]
            if data.market.institutional
            else 0
        )

        # --------------------------------------------------------
        # OI / PCR
        # --------------------------------------------------------

        pcr = float(data.market.pcr)

        scores["oi_pcr"] = (
            self.WEIGHTS["oi_pcr"]
            if 0.8 <= pcr <= 1.2
            else self.WEIGHTS["oi_pcr"] // 2
        )

        # --------------------------------------------------------
        # VWAP
        # --------------------------------------------------------

        vwap_relation = str(
            data.market.vwap_relation or ""
        ).strip().lower()

        scores["vwap"] = (
            self.WEIGHTS["vwap"]
            if vwap_relation == "above"
            else 0
        )

        # --------------------------------------------------------
        # ATR
        # --------------------------------------------------------

        scores["atr"] = (
            self.WEIGHTS["atr"]
            if float(data.market.atr) > 0
            else 0
        )

        # --------------------------------------------------------
        # Spread
        # --------------------------------------------------------

        scores["spread"] = (
            self.WEIGHTS["spread"]
            if float(data.market.spread) < 1
            else 0
        )

        # --------------------------------------------------------
        # News
        #
        # Existing project behavior:
        # no active news risk = full points.
        # --------------------------------------------------------

        scores["news"] = (
            0
            if data.market.news
            else self.WEIGHTS["news"]
        )

        # --------------------------------------------------------
        # Total
        # --------------------------------------------------------

        total = sum(scores.values())

        # --------------------------------------------------------
        # Grade
        # --------------------------------------------------------

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

        # --------------------------------------------------------
        # Execution gate
        # --------------------------------------------------------

        execute = total >= 80

        # --------------------------------------------------------
        # Explainability
        # --------------------------------------------------------

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
# RISK MANAGER
# ============================================================


class RiskManager:
    """
    Lightweight scoring-level risk gate.

    This is NOT the canonical trading RiskEngine.

    The canonical RiskEngine remains responsible for actual
    order-level risk validation before broker submission.
    """

    MIN_EXECUTION_SCORE = 80

    def evaluate(
        self,
        score: SignalScore,
    ) -> RiskGateResult:

        if score.total_score < self.MIN_EXECUTION_SCORE:
            return RiskGateResult(
                allowed=False,
                reason="Low score",
            )

        return RiskGateResult(
            allowed=True,
            reason="Approved",
        )


# ============================================================
# ANALYTICS
# ============================================================


class TradeAnalytics:
    """
    Lightweight analytics hook.

    Persistence should be handled by the canonical execution
    lifecycle, not by this class.
    """

    def record(
        self,
        order: dict,
        score: SignalScore,
    ) -> None:

        print(
            f"Analytics -> "
            f"{order['symbol']} "
            f"Score={score.total_score}"
        )


# ============================================================
# FEEDBACK
# ============================================================


class FeedbackEngine:
    """
    Lightweight feedback hook.

    This does not place or modify orders.
    """

    def learn(
        self,
        order: dict,
        score: SignalScore,
    ) -> None:

        print(
            f"Learning from {order['symbol']}"
        )


# ============================================================
# STRATEGY SERVICE
# ============================================================


class TradingService:
    """
    Legacy/simple strategy signal producer.

    Real execution should ultimately flow through the canonical
    execution pipeline.
    """

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
# DECISION PIPELINE
# ============================================================


class DecisionPipelineService:

    def __init__(self) -> None:

        self.decision = TradingDecision(
            confidence=90,
            sentiment="Bullish",
        )


# ============================================================
# LEGACY ANALYSIS ORCHESTRATOR
# ============================================================


class TradingOrchestrator:
    """
    Scoring/analysis orchestrator.

    IMPORTANT:
    This class intentionally does NOT instantiate an OMS.

    The canonical OMS is:

        Backend.application.order_management.OrderManagementService

    Broker execution belongs to the execution lifecycle/pipeline.
    """

    def __init__(self) -> None:

        self.pipeline = DecisionPipelineService()
        self.trading_service = TradingService()
        self.scoring = SignalScoringEngine()
        self.risk = RiskManager()
        self.analytics = TradeAnalytics()
        self.feedback = FeedbackEngine()

    def execute(
        self,
        market: MarketDataInputs,
        strategy: str,
    ) -> list[dict]:

        signals = self.trading_service.run_strategy(
            strategy,
            market,
        )

        results: list[dict] = []

        for signal in signals:

            score = self.scoring.score(
                SignalScoringInput(
                    signal=signal,
                    market=market,
                    decision=self.pipeline.decision,
                    strategy_name=strategy,
                )
            )

            # ----------------------------------------------------
            # Score rejected
            # ----------------------------------------------------

            if not score.execute:

                results.append(
                    {
                        "status": "REJECTED",
                        "reason": "Score below execution threshold",
                        "symbol": signal.symbol,
                        "action": signal.action,
                        "score": score,
                    }
                )

                continue

            # ----------------------------------------------------
            # Risk gate
            # ----------------------------------------------------

            gate = self.risk.evaluate(score)

            if not gate.allowed:

                results.append(
                    {
                        "status": "REJECTED",
                        "reason": gate.reason,
                        "symbol": signal.symbol,
                        "action": signal.action,
                        "score": score,
                    }
                )

                continue

            # ----------------------------------------------------
            # IMPORTANT
            #
            # Do NOT call a local/duplicate OMS here.
            #
            # The canonical execution path must handle order
            # conversion, risk validation, persistence, broker
            # submission, retry/reconciliation and lifecycle.
            # ----------------------------------------------------

            result = {
                "status": "APPROVED",
                "symbol": signal.symbol,
                "action": signal.action,
                "score": score,
                "risk": gate,
            }

            self.analytics.record(
                {
                    "symbol": signal.symbol,
                    "action": signal.action,
                    "status": "APPROVED",
                },
                score,
            )

            self.feedback.learn(
                {
                    "symbol": signal.symbol,
                    "action": signal.action,
                    "status": "APPROVED",
                },
                score,
            )

            results.append(result)

        return results


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

    results = orchestrator.execute(
        market,
        "breakout",
    )

    for result in results:
        print(result)