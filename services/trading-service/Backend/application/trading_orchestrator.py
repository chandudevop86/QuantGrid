from Backend.application.decision_pipeline import DecisionPipelineService
from Backend.application.signal_scoring_engine import SignalScoringEngine

from Backend.application.risk_engine import RiskEngine
from Backend.application.trading_service import TradingService
from Backend.application.order_management import OrderManagementService
from Backend.application.trade_analytics_engine import TradeAnalyticsService
from Backend.application.feedback_engine import FeedbackEngine
from Backend.application.strategy_selection_engine import (
    StrategySelector,
    StrategySelectionInput
)

class TradingOrchestrator:

    def __init__(self,trade_repository):
        self.pipeline = DecisionPipelineService()
        self.trade_repository = trade_repository
        self.scoring = SignalScoringEngine()
        self.selector = StrategySelector()
        self.risk = RiskEngine()
        self.trading_service = TradingService()
        self.oms = OrderManagementService( broker="dhan")
        self.analytics = TradeAnalyticsService()
        self.feedback = FeedbackEngine(trade_repository=self.trade_repository)

    def execute_cycle(self, market):

        # 1. AI Decision
        decision = self.pipeline.run(
            market,
            risk_blocked=False
        )

        # 2. Select strategy
        strategy_input = StrategySelectionInput(

            trend=market.trend or "Unknown",

            market_regime=getattr(
                market,
                "market_regime",
                "Unknown"
            ),

            volatility=getattr(
                market,
                "volatility",
                "Normal"
            ),

            volume=getattr(
                market,
                "volume",
                "Normal"
            ),

            oi_bias=market.oi_bias or "Neutral",

            vwap_relation=market.vwap_relation or "Unknown",

            confidence=getattr(
                decision,
                "confidence",
                50
            ),

            risk_reward=2.0,

            liquidity=getattr(
                market,
                "liquidity",
                "Normal"
            ),

            expiry_day=market.expiry_day,

            news_driven=getattr(
                market,
                "news",
                False
            )
        )


        strategy_result = self.selector.select(
            strategy_input
        )


        strategy = strategy_result.strategy_name


        # 3. Generate trading signal
        signals = self.trading_service.run_strategy(
            strategy_name=strategy,
            data=market.candles,
            symbol=market.symbol,
            capital=market.capital,
            risk_pct=(
                market.risk_per_trade / market.capital
                if market.capital
                else 0.01
            ),
            params={
                "market": market
            }
        )

        if not signals:
                print(
                        f"No signals generated for strategy={strategy}"
                )
                return None
                

        signal = signals[0]
        print(
                "Generated Signal:",
                            signal
                )

        # 4. Score signal
        score = self.scoring.score(
            SignalScoringInput(
                signal=signal,
                market=market,
                decision=decision,
                strategy_name=strategy
            )
        )


        # 5. Risk validation
        approval = self.risk.validate(
            strategy,
            score
        )


        if not approval.allowed:

            return approval
        print(
            "Risk rejected:",
            approval
        )


        # 6. Create trade
        trade = self.trading_service.generate_trade(
            strategy=strategy,
            signal=signal,
        )



        # 7. Execute order
        order = self.oms.execute(
            trade
        )



        # 8. Analytics
        self.analytics.record(
            order
        )



        # 9. Feedback
        self.feedback.update(
            order
        )

        print(
                "Order Created:",
                order
        )
        return order