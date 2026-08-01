from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.portfolio.application.schemas.common import ORMBaseModel


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()


class WatchlistItemRead(ORMBaseModel):
    id: UUID
    watchlist_id: UUID
    symbol: str
    notes: str | None
    added_at: datetime


class WatchlistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    items: list[WatchlistItemCreate] = Field(default_factory=list)


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class WatchlistRead(ORMBaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    items: list[WatchlistItemRead] = Field(default_factory=list)
