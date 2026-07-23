class TradingOrchestrator:

    def __init__(self):

        self.pipeline = DecisionPipelineService()

        self.trading_service = TradingService()

        self.scoring = SignalScoringEngine()

        self.oms = OrderManagementService(...)

        self.analytics = TradeAnalytics()

        self.feedback = FeedbackEngine()