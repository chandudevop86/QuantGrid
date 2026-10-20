from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from Backend.application.investment_research_service import (
    latest_investment_dashboard,
    latest_mutual_fund_research,
    latest_stock_research,
    run_multibagger_predictor,
)
from Backend.application.quality_growth_screener import latest_quality_growth_screen
from Backend.core.database import get_db
from Backend.presentation.api.roles import require_roles

router = APIRouter(prefix="/investing", tags=["investing"])

_LEGACY_NOTICE = (
    "Educational research, not financial advice. "
    "Legacy investment research uses illustrative/sample inputs without verified data "
    "provenance. Rankings, fund names and allocations are disabled in production. "
    "Use the separate licensed Quality Growth V2 read-only screen."
)
_LEGACY_CATEGORIES = (
    "multibagger_candidates", "top_stock_picks", "watchlist_stocks", "avoid_stocks",
    "top_mutual_funds", "sip_ideas", "sector_trend", "risk_alerts",
)


def _legacy_demo_only() -> bool:
    """Only allow historical sample output outside production, prominently tagged."""
    return os.getenv("QUANTGRID_ENV", "local").strip().lower() not in {"prod", "production"}


def _legacy_empty() -> dict:
    return {
        "items": [], "data_status": "UNVERIFIED", "reason": _LEGACY_NOTICE,
        "disclaimer": _LEGACY_NOTICE,
    }


def _legacy_dashboard_empty() -> dict:
    return {
        "data_status": "UNVERIFIED", "generated_at": None,
        "summary": "Legacy sample research is disabled until verified licensed data is available.",
        "cards": {key: [] for key in _LEGACY_CATEGORIES},
        "stocks": [], "multibagger_predictions": [], "mutual_funds": [],
        "disclaimer": _LEGACY_NOTICE,
    }



@router.get("/stocks/research")
def stocks_research(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    if not _legacy_demo_only():
        return _legacy_empty()
    return {
        "items": latest_stock_research(db=db),
        "data_status": "DEMO_ONLY", "disclaimer": _LEGACY_NOTICE,
    }


@router.get("/stocks/quality-growth")
def stock_quality_growth(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    """Read-only auto-refreshed V2 watchlist. No sample or order data."""
    return latest_quality_growth_screen()


@router.get("/stocks/top-picks")
def stock_top_picks(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    if not _legacy_demo_only():
        return _legacy_empty()
    items = latest_stock_research(db=db)
    picks = [item for item in items if item.get("recommendation") in {"BUY", "HOLD"}]
    return {"items": sorted(picks, key=lambda item: item.get("total_score", 0), reverse=True)[:10],
            "data_status": "DEMO_ONLY", "disclaimer": _LEGACY_NOTICE}


@router.get("/stocks/multibagger-predictor")
def stock_multibagger_predictor(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    if not _legacy_demo_only():
        return _legacy_empty()
    return {
        "items": [item.model_dump() for item in run_multibagger_predictor()],
        "data_status": "DEMO_ONLY", "disclaimer": _LEGACY_NOTICE,
    }


@router.get("/mutual-funds/research")
def mutual_funds_research(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    if not _legacy_demo_only():
        return _legacy_empty()
    return {
        "items": latest_mutual_fund_research(db=db),
        "data_status": "DEMO_ONLY", "disclaimer": _LEGACY_NOTICE,
    }


@router.get("/mutual-funds/top-picks")
def mutual_fund_top_picks(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    if not _legacy_demo_only():
        return _legacy_empty()
    items = latest_mutual_fund_research(db=db)
    picks = [item for item in items if item.get("recommendation") in {"BUY", "HOLD"}]
    return {"items": sorted(picks, key=lambda item: item.get("total_score", 0), reverse=True)[:10],
            "data_status": "DEMO_ONLY", "disclaimer": _LEGACY_NOTICE}


@router.get("/dashboard")
def investing_dashboard(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    if not _legacy_demo_only():
        return _legacy_dashboard_empty()
    dashboard = latest_investment_dashboard(db=db)
    return {**dashboard, "data_status": "DEMO_ONLY", "disclaimer": _LEGACY_NOTICE}
