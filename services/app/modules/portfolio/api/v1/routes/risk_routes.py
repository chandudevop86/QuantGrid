from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, get_current_user
from app.modules.portfolio.api.v1.deps import get_risk_service
from app.modules.portfolio.application.schemas.risk import RiskMetricsResponse
from app.modules.portfolio.application.services.risk_service import RiskService

router = APIRouter(prefix="/portfolios/{portfolio_id}/risk", tags=["Risk"])


@router.get("", response_model=RiskMetricsResponse)
async def get_risk_metrics(
    portfolio_id: UUID,
    lookback_days: int = Query(default=365, ge=30, le=3650),
    risk_free_rate_annual: float = Query(default=0.06, ge=0, le=1),
    current_user: CurrentUser = Depends(get_current_user),
    service: RiskService = Depends(get_risk_service),
) -> RiskMetricsResponse:
    """Sharpe ratio, Sortino ratio, annualized volatility, max drawdown, beta, and alpha."""
    return await service.get_risk_metrics(
        current_user.id,
        portfolio_id,
        lookback_days=lookback_days,
        risk_free_rate_annual=risk_free_rate_annual,
    )
