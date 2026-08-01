from __future__ import annotations

from pydantic import BaseModel


class AllocationSliceResponse(BaseModel):
    label: str
    value: float
    weight_percent: float


class AllocationResponse(BaseModel):
    portfolio_id: str
    slices: list[AllocationSliceResponse]


class TopHoldingsResponse(BaseModel):
    portfolio_id: str
    holdings: list[AllocationSliceResponse]


class DiversificationScoreResponse(BaseModel):
    portfolio_id: str
    diversification_score: float


class HealthScoreResponse(BaseModel):
    portfolio_id: str
    overall_score: float
    diversification_component: float
    concentration_component: float
    volatility_component: float
    asset_mix_component: float
    notes: list[str]


class BenchmarkComparisonResponse(BaseModel):
    portfolio_id: str
    benchmark_symbol: str | None
    portfolio_return_percent: float
    benchmark_return_percent: float
    excess_return_percent: float
    outperforming: bool
