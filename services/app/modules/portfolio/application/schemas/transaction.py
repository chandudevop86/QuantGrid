from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.portfolio.application.schemas.common import ORMBaseModel
from app.modules.portfolio.domain.enums import TransactionType


class TransactionCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    transaction_type: TransactionType
    quantity: Decimal = Field(..., ge=0)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    transaction_date: date
    split_ratio_from: Decimal | None = Field(default=None, gt=0)
    split_ratio_to: Decimal | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("transaction_date")
    @classmethod
    def _not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("transaction_date cannot be in the future.")
        return v

    @model_validator(mode="after")
    def _validate_by_type(self) -> "TransactionCreate":
        if self.transaction_type in (TransactionType.BUY, TransactionType.SELL):
            if self.quantity <= 0:
                raise ValueError(f"{self.transaction_type.value} requires quantity > 0.")
            if self.price <= 0:
                raise ValueError(f"{self.transaction_type.value} requires price > 0.")
        elif self.transaction_type == TransactionType.DIVIDEND:
            if self.price <= 0:
                raise ValueError("DIVIDEND requires the per-share (or total) amount in 'price' > 0.")
        elif self.transaction_type == TransactionType.BONUS:
            if self.quantity <= 0:
                raise ValueError("BONUS requires quantity (bonus shares issued) > 0.")
        elif self.transaction_type == TransactionType.SPLIT:
            if not self.split_ratio_from or not self.split_ratio_to:
                raise ValueError(
                    "SPLIT requires both split_ratio_from and split_ratio_to (e.g. 1 -> 2 for a 2:1 split)."
                )
        return self


class TransactionRead(ORMBaseModel):
    id: UUID
    portfolio_id: UUID
    symbol: str
    transaction_type: TransactionType
    quantity: Decimal
    price: Decimal
    fees: Decimal
    transaction_date: date
    split_ratio_from: Decimal | None
    split_ratio_to: Decimal | None
    notes: str | None
    created_at: datetime
