from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ReturnMetric(BaseModel):
    label: str
    value_percent: float


class PerformanceResponse(BaseModel):
    portfolio_id: str
    as_of: date
    daily_return_percent: float | None = None
    weekly_return_percent: float | None = None
    monthly_return_percent: float | None = None
    yearly_return_percent: float | None = None
    absolute_return_percent: float | None = None
    xirr_percent: float | None = None
    warnings: list[str] = []
