from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from Backend.application.investment_research_service import (
    latest_investment_dashboard,
    latest_mutual_fund_research,
    latest_stock_research,
)
from Backend.core.database import get_db
from Backend.presentation.api.roles import require_roles

router = APIRouter(prefix="/investing", tags=["investing"])


@router.get("/stocks/research")
def stocks_research(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    return {
        "items": latest_stock_research(db=db),
        "disclaimer": "Educational research, not financial advice.",
    }


@router.get("/stocks/top-picks")
def stock_top_picks(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    items = latest_stock_research(db=db)
    picks = [item for item in items if item.get("recommendation") in {"BUY", "HOLD"}]
    return {"items": sorted(picks, key=lambda item: item.get("total_score", 0), reverse=True)[:10]}


@router.get("/mutual-funds/research")
def mutual_funds_research(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    return {
        "items": latest_mutual_fund_research(db=db),
        "disclaimer": "Educational research, not financial advice.",
    }


@router.get("/mutual-funds/top-picks")
def mutual_fund_top_picks(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    items = latest_mutual_fund_research(db=db)
    picks = [item for item in items if item.get("recommendation") in {"BUY", "HOLD"}]
    return {"items": sorted(picks, key=lambda item: item.get("total_score", 0), reverse=True)[:10]}


@router.get("/dashboard")
def investing_dashboard(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    return latest_investment_dashboard(db=db)
