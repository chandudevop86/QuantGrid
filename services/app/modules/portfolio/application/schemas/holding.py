from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.portfolio.application.schemas.common import ORMBaseModel
from app.modules.portfolio.domain.enums import AssetClass, MarketCapSegment


class HoldingCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=200)
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    average_cost: Decimal = Field(default=Decimal("0"), ge=0)
    sector: str | None = Field(default=None, max_length=100)
    asset_class: AssetClass = AssetClass.EQUITY
    market_cap_segment: MarketCapSegment = MarketCapSegment.NOT_APPLICABLE
    beta: Decimal | None = None

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()


class HoldingUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    sector: str | None = Field(default=None, max_length=100)
    asset_class: AssetClass | None = None
    market_cap_segment: MarketCapSegment | None = None
    beta: Decimal | None = None


class HoldingRead(ORMBaseModel):
    id: UUID
    portfolio_id: UUID
    symbol: str
    name: str | None
    quantity: Decimal
    average_cost: Decimal
    sector: str | None
    asset_class: AssetClass
    market_cap_segment: MarketCapSegment
    beta: Decimal | None
    created_at: datetime
    updated_at: datetime


class HoldingWithMarketData(HoldingRead):
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    invested_value: Decimal
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_percent: float | None = None
