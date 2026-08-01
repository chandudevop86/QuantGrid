from __future__ import annotations

from pydantic import BaseModel


class RiskMetricsResponse(BaseModel):
    portfolio_id: str
    volatility_percent: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown_percent: float | None = None
    beta: float | None = None
    alpha_percent: float | None = None
    benchmark_symbol: str | None = None
    warnings: list[str] = []
