class InMemoryTradeRepository:

    def __init__(self):
        self.trades = []


    def save(self, trade):
        self.trades.append(trade)


    def get_trades(self, strategy=None):

        if strategy:
            return [
                t for t in self.trades
                if t.strategy == strategy
            ]

        return 
self.tradesrepository = InMemoryTradeRepository()

orchestrator = TradingOrchestrator(
    trade_repository=repository
)
    