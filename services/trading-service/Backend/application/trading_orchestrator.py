from Backend.application.decision_pipeline import DecisionPipelineService
from Backend.application.signal_scoring_engine import SignalScoringEngine
from Backend.application.strategy_selection_engine import StrategySelector
from Backend.application.risk_engine import RiskEngine
from Backend.application.trading_service import TradingService
from Backend.application.order_management import OrderManagementService
from Backend.application.trade_analytics_engine import TradeAnalyticsService
from Backend.application.feedback_engine import FeedbackEngine


class TradingOrchestrator:

    def __init__(self):
        self.pipeline = DecisionPipelineService()
        self.scoring = SignalScoringEngine()
        self.selector = StrategySelector()
        self.risk = RiskEngine()
        self.trading_service = TradingService()
        self.oms = OrderManagementService( broker="dhan")
        self.analytics = TradeAnalyticsService()
        self.feedback = FeedbackEngine()

    def execute_cycle(self):

        # 1. Collect market snapshot
        market = self.pipeline.collect_market_data()

        # 2. Score signal quality
        signal = self.scoring.score(market)

        # 3. Select best strategy
        strategy = self.selector.select(signal)

        # 4. Risk validation
        approval = self.risk.validate(strategy, signal)

        if not approval.allowed:
            return approval

        # 5. Create trade
        trade = self.trading_service.generate_trade(
            strategy=strategy,
            signal=signal,
        )

        # 6. Execute order
        order = self.oms.execute(trade)

        # 7. Record analytics
        self.analytics.record(order)

        # 8. Learn from execution
        self.feedback.update(order)

        return order