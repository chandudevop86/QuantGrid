from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.portfolio.application.schemas.common import ORMBaseModel
from app.modules.portfolio.domain.enums import AlertDirection, AlertStatus, AlertType


class AlertCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    portfolio_id: UUID | None = None
    alert_type: AlertType
    direction: AlertDirection
    threshold_price: Decimal = Field(..., gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()


class AlertUpdate(BaseModel):
    threshold_price: Decimal | None = Field(default=None, gt=0)
    direction: AlertDirection | None = None
    status: AlertStatus | None = None
    notes: str | None = Field(default=None, max_length=500)


class AlertRead(ORMBaseModel):
    id: UUID
    user_id: UUID
    portfolio_id: UUID | None
    symbol: str
    alert_type: AlertType
    direction: AlertDirection
    threshold_price: Decimal
    status: AlertStatus
    triggered_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
