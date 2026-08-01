from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.portfolio.application.schemas.common import ORMBaseModel
from app.modules.portfolio.domain.enums import Currency, PortfolioType


class PortfolioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    portfolio_type: PortfolioType = PortfolioType.EQUITY
    base_currency: Currency = Currency.USD
    benchmark_symbol: str | None = Field(default="^GSPC", max_length=20)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    portfolio_type: PortfolioType | None = None
    benchmark_symbol: str | None = Field(default=None, max_length=20)
    is_archived: bool | None = None


class PortfolioRead(ORMBaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    portfolio_type: PortfolioType
    base_currency: Currency
    benchmark_symbol: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class PortfolioSummary(ORMBaseModel):
    """Portfolio read model enriched with current valuation totals."""

    id: UUID
    name: str
    portfolio_type: PortfolioType
    base_currency: Currency
    total_market_value: Decimal
    total_invested_value: Decimal
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_percent: float
    holdings_count: int
