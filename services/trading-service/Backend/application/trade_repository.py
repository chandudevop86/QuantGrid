from typing import Any


class InMemoryTradeRepository:
    """
    Simple in-memory repository for testing.
    Replace with PostgreSQL repository in production.
    """

    def __init__(self):
        self.trades: list[Any] = []


    def save(self, trade):
        self.trades.append(trade)


    def get_trades(self, strategy=None):

        if strategy:

            return [
                trade
                for trade in self.trades
                if getattr(trade, "strategy", None) == strategy
            ]

        return self.trades



class TradeRepository:

    def __init__(self):

        self.repository = InMemoryTradeRepository()


    def save(self, trade):

        self.repository.save(
            trade
        )


    def get_trades(self, strategy=None):

        return self.repository.get_trades(
            strategy
        )