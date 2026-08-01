from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.portfolio.domain.enums import (
    AssetClass,
    MarketCapSegment,
    TransactionType,
)


@dataclass(frozen=True, slots=True)
class Money:
    """Value object representing a monetary amount in a given currency."""

    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount is None:
            raise ValueError("Money amount cannot be None")

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: {self.currency} vs {other.currency}"
            )


@dataclass(frozen=True, slots=True)
class CashFlow:
    """A single dated cash flow, used for XIRR / money-weighted return calculations."""

    when: date
    amount: float  # negative = outflow (buy/investment), positive = inflow (sell/dividend/current value)


@dataclass(frozen=True, slots=True)
class PricePoint:
    """A single (date, price) observation used for time-series based return/risk metrics."""

    as_of: date
    close_price: float


@dataclass(slots=True)
class HoldingLot:
    """Represents an accumulated position lot used by the average-cost engine."""

    quantity: float
    unit_cost: float


@dataclass(slots=True)
class HoldingSnapshot:
    """A framework-agnostic snapshot of a holding, used by pure calculation engines."""

    symbol: str
    quantity: float
    average_cost: float
    current_price: float
    sector: str | None = None
    asset_class: AssetClass = AssetClass.EQUITY
    market_cap_segment: MarketCapSegment = MarketCapSegment.NOT_APPLICABLE
    beta: float | None = None

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def invested_value(self) -> float:
        return self.quantity * self.average_cost

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.invested_value

    @property
    def unrealized_pnl_percent(self) -> float:
        if self.invested_value == 0:
            return 0.0
        return (self.unrealized_pnl / self.invested_value) * 100.0


@dataclass(slots=True)
class TransactionRecord:
    """Framework-agnostic transaction, consumed by the average-cost / lot engine."""

    id: UUID | None
    symbol: str
    transaction_type: TransactionType
    quantity: float
    price: float
    fees: float
    transaction_date: date
    split_ratio_from: float | None = None
    split_ratio_to: float | None = None


@dataclass(slots=True)
class PortfolioMetricsInput:
    """Aggregate input bundle used to feed the analytics/performance engines."""

    holdings: list[HoldingSnapshot] = field(default_factory=list)
    cash_flows: list[CashFlow] = field(default_factory=list)
    nav_history: list[PricePoint] = field(default_factory=list)
    benchmark_history: list[PricePoint] = field(default_factory=list)
    risk_free_rate_annual: float = 0.06
