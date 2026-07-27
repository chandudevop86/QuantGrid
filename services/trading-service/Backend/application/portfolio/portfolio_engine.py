"""
QuantGrid Portfolio Engine

Responsibilities
----------------
* Maintain positions
* Update positions after executions
* Calculate average price
* Realised P&L
* Unrealised P&L
* Portfolio market value

Used by:
- execution engine
- holdings service
- pnl engine
- exposure engine
- dashboard
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict
from datetime import datetime
from threading import RLock
from uuid import uuid4

# ==========================================================
# Position
# ==========================================================


@dataclass
class Position:

    account_id: str

    symbol: str

    exchange: str

    product: str

    instrument_type: str

    side: str

    quantity: int

    average_price: float

    last_price: float

    realised_pnl: float

    unrealised_pnl: float

    brokerage: float

    taxes: float

    charges: float

    margin_used: float

    created_at: datetime

    updated_at: datetime
    def market_value(self) -> float:
        return self.quantity * self.last_price

    def cost_value(self) -> float:
        return self.quantity * self.average_price

    def update_price(self, price: float):

        self.last_price = price

        if self.quantity != 0:

            if self.side == "LONG":

                self.unrealised_pnl = (
                    self.last_price - self.average_price
                ) * self.quantity

            else:

                self.unrealised_pnl = (
                    self.average_price - self.last_price
                ) * self.quantity

            self.updated_at = datetime.utcnow()

# ==========================================================
# Portfolio
# ==========================================================


@dataclass
class Portfolio:

    account_id: str

    cash: float = 0.0

    positions: Dict[str, Position] = field(default_factory=dict)

    def get_position(self, symbol: str) -> Position:

        if symbol not in self.positions:

            self.positions[symbol] = Position(
                account_id=self.account_id,
                symbol=symbol,
                )

        return self.positions[symbol]

    # -----------------------------------------------------

    def buy(
        self,
        symbol: str,
        qty: int,
        price: float,
    ):

        position = self.get_position(symbol)

        total_cost = (
            position.average_price * position.quantity
        ) + (price * qty)

        position.quantity += qty

        position.average_price = (
            total_cost / position.quantity
        )

        position.side = "LONG"

        position.last_price = price

        self.cash -= qty * price

    # -----------------------------------------------------

    def sell(
        self,
        symbol: str,
        qty: int,
        price: float,
    ):

        position = self.get_position(symbol)

        if qty > position.quantity:

            raise ValueError(
                f"Cannot sell {qty}. Holding only {position.quantity}"
            )

        realised = (
            price - position.average_price
        ) * qty

        position.realised_pnl += realised

        position.quantity -= qty

        position.last_price = price

        self.cash += qty * price

        if position.quantity == 0:

            position.average_price = 0.0

            position.unrealised_pnl = 0.0

    # -----------------------------------------------------

    def mark_price(
        self,
        symbol: str,
        market_price: float,
    ):

        if symbol not in self.positions:
            return

        self.positions[symbol].update_price(market_price)

    # -----------------------------------------------------

    def total_market_value(self):

        return sum(
            p.market_value()
            for p in self.positions.values()
        )

    # -----------------------------------------------------

    def total_cost(self):

        return sum(
            p.cost_value()
            for p in self.positions.values()
        )

    # -----------------------------------------------------

    def total_realised_pnl(self):

        return sum(
            p.realised_pnl
            for p in self.positions.values()
        )

    # -----------------------------------------------------

    def total_unrealised_pnl(self):

        return sum(
            p.unrealised_pnl
            for p in self.positions.values()
        )

    # -----------------------------------------------------

    def total_equity(self):

        return (
            self.cash
            + self.total_market_value()
        )

    # -----------------------------------------------------

    def portfolio_summary(self):

        return {

            "cash": self.cash,

            "market_value": self.total_market_value(),

            "cost": self.total_cost(),

            "realised_pnl": self.total_realised_pnl(),

            "unrealised_pnl": self.total_unrealised_pnl(),

            "equity": self.total_equity(),

            "positions": len(self.positions),

        }


# ==========================================================
# Portfolio Engine
# ==========================================================


class PortfolioEngine:

    """
    Central Portfolio Manager.

    Future:
    - Redis
    - PostgreSQL
    - Multi-account
    - Risk engine integration
    """

    def __init__(self):

        self.portfolios: Dict[str, Portfolio] = {}

    # -------------------------------------------------

    def portfolio(
        self,
        account_id: str,
    ) -> Portfolio:

        if account_id not in self.portfolios:

            self.portfolios[account_id] = Portfolio(
                account_id=account_id
            )

        return self.portfolios[account_id]

    # -------------------------------------------------

    def execute_trade(

        self,

        account_id: str,

        symbol: str,

        side: str,

        quantity: int,

        price: float,

    ):

        portfolio = self.portfolio(account_id)

        side = side.upper()

        if side == "BUY":

            portfolio.buy(
                symbol,
                quantity,
                price,
            )

        elif side == "SELL":

            portfolio.sell(
                symbol,
                quantity,
                price,
            )

        else:

            raise ValueError(
                "Invalid trade side"
            )

    # -------------------------------------------------

    def update_market_price(

        self,

        symbol: str,

        price: float,

    ):

        for portfolio in self.portfolios.values():

            portfolio.mark_price(
                symbol,
                price,
            )

    # -------------------------------------------------

    def summary(
        self,
        account_id: str,
    ):

        return self.portfolio(
            account_id
        ).portfolio_summary()