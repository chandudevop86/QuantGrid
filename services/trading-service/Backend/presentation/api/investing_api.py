from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from Backend.application.investment_research_service import (
    ResearchDataUnavailable,
    _demo_mode_allowed,
    latest_investment_dashboard,
    latest_mutual_fund_research,
    latest_stock_research,
    run_multibagger_predictor,
)
from Backend.core.database import get_db
from Backend.presentation.api.roles import require_roles

router = APIRouter(prefix="/investing", tags=["investing"])


def _research_unavailable(exc: ResearchDataUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "RESEARCH_DATA_UNAVAILABLE",
            "message": str(exc),
        },
    )


@router.get("/stocks/research")
def stocks_research(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    try:
        return {
            "items": latest_stock_research(db=db, demo=_demo_mode_allowed()),
            "disclaimer": "Educational research, not financial advice.",
        }
    except ResearchDataUnavailable as exc:
        raise _research_unavailable(exc) from exc


@router.get("/stocks/top-picks")
def stock_top_picks(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    try:
        items = latest_stock_research(db=db, demo=_demo_mode_allowed())
    except ResearchDataUnavailable as exc:
        raise _research_unavailable(exc) from exc
    picks = [item for item in items if item.get("recommendation") in {"BUY", "HOLD"}]
    return {"items": sorted(picks, key=lambda item: item.get("total_score", 0), reverse=True)[:10]}


@router.get("/stocks/multibagger-predictor")
def stock_multibagger_predictor(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    try:
        items = run_multibagger_predictor(demo=_demo_mode_allowed())
    except ResearchDataUnavailable as exc:
        raise _research_unavailable(exc) from exc
    return {
        "items": [item.model_dump() for item in items],
        "disclaimer": "Educational research, not financial advice.",
    }


@router.get("/mutual-funds/research")
def mutual_funds_research(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    try:
        return {
            "items": latest_mutual_fund_research(db=db, demo=_demo_mode_allowed()),
            "disclaimer": "Educational research, not financial advice.",
        }
    except ResearchDataUnavailable as exc:
        raise _research_unavailable(exc) from exc


@router.get("/mutual-funds/top-picks")
def mutual_fund_top_picks(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    try:
        items = latest_mutual_fund_research(db=db, demo=_demo_mode_allowed())
    except ResearchDataUnavailable as exc:
        raise _research_unavailable(exc) from exc
    picks = [item for item in items if item.get("recommendation") in {"BUY", "HOLD"}]
    return {"items": sorted(picks, key=lambda item: item.get("total_score", 0), reverse=True)[:10]}


@router.get("/dashboard")
def investing_dashboard(
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
    db: Session = Depends(get_db),
):
    try:
        return latest_investment_dashboard(db=db, demo=_demo_mode_allowed())
    except ResearchDataUnavailable as exc:
        raise _research_unavailable(exc) from exc
