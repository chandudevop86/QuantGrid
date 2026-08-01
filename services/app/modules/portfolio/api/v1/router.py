from __future__ import annotations

from fastapi import APIRouter

from app.modules.portfolio.api.v1.routes import (
    alert_routes,
    analytics_routes,
    holding_routes,
    performance_routes,
    portfolio_routes,
    rebalancing_routes,
    risk_routes,
    transaction_routes,
    watchlist_routes,
)

router = APIRouter()

router.include_router(portfolio_routes.router)
router.include_router(holding_routes.router)
router.include_router(transaction_routes.router)
router.include_router(performance_routes.router)
router.include_router(risk_routes.router)
router.include_router(analytics_routes.router)
router.include_router(rebalancing_routes.router)
router.include_router(watchlist_routes.router)
router.include_router(alert_routes.router)
