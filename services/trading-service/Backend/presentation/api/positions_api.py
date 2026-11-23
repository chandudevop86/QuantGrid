from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.application.job_queue import enqueue_job
from Backend.application.position_store import list_closed_positions, list_open_positions, position_summary
from Backend.application.options.paper_order_ledger import list_option_positions
from Backend.application.trade_exit_engine import evaluate_exit_rule, exit_all_positions, exit_position, exit_rules, monitor_open_positions
from Backend.core.database import get_db
from Backend.domain.security.models import User
from Backend.presentation.api.roles import current_user, require_roles
from Backend.presentation.api.upstream_errors import upstream_service_error


router = APIRouter(prefix="/positions", tags=["positions"])


class ExitRequest(BaseModel):
    reason: str = Field(default="manual_exit")
    exit_price: float | None = Field(default=None, gt=0)


def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode


def _option_position(row: dict) -> dict:
    # Negative IDs keep the option ledger distinct from generic position IDs.
    return {**row, "id": -int(row["id"]), "option_order_id": int(row["id"])}


def _paper_options(execution_mode: str, position_status: str) -> list[dict]:
    if execution_mode != "paper":
        return []
    return [_option_position(row) for row in list_option_positions()
            if row["status"] == position_status]


@router.get("/open")
def open_positions(
    _role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    return {"positions": list_open_positions(execution_mode=execution_mode) + _paper_options(execution_mode, "open")}


@router.get("/closed")
def closed_positions(
    _role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    return {"positions": list_closed_positions(execution_mode=execution_mode) + _paper_options(execution_mode, "closed")}


@router.get("/summary")
def summary(
    _role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    return position_summary(execution_mode=execution_mode)


@router.get("/exit-rules")
def get_exit_rules(_role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops"))):
    evaluations = []
    for position in list_open_positions():
        decision = evaluate_exit_rule(position)
        evaluations.append(
            {
                "position_id": position.get("id"),
                "symbol": position.get("symbol"),
                "should_exit": decision.should_exit,
                "reason": decision.reason,
                "price": decision.price,
                "details": decision.details or {},
            }
        )
    return {"rules": exit_rules(), "open_positions": evaluations}


@router.post("/exit-monitor")
async def run_exit_monitor_now(
    request: Request,
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    try:
        result = await monitor_open_positions(
            db=db,
            actor=actor,
            request=request,
            execution_mode=execution_mode,
        )
        if execution_mode == "paper":
            from Backend.application.options.auto_paper_execution import monitor_option_positions

            result["option_paper"] = monitor_option_positions()
        return result
    except Exception as exc:
        raise upstream_service_error("broker", "exit_monitor", exc) from exc


@router.post("/exit-monitor/jobs")
def enqueue_exit_monitor_job(
    _role: str = Depends(require_roles("admin", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    return enqueue_job(
        "exit-monitor",
        {"execution_mode": execution_mode},
        metadata={"job_type": "exit-monitor", "execution_mode": execution_mode, "status": "queued"},
    )


@router.post("/{position_id}/exit")
async def exit_single_position(
    position_id: int,
    request: Request,
    payload: ExitRequest | None = Body(default=None),
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    if position_id < 0:
        if execution_mode != "paper":
            raise HTTPException(status_code=400, detail="Option paper positions require paper mode.")
        from Backend.application.options.auto_paper_execution import exit_option_paper

        try:
            position = exit_option_paper(-position_id, reason=(payload or ExitRequest()).reason)
            return {"position": _option_position(position), "execution_mode": "paper"}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise upstream_service_error("market_data", "option_paper_exit", exc) from exc
    try:
        return await exit_position(
            position_id,
            db=db,
            actor=actor,
            request=request,
            execution_mode=execution_mode,
            reason=(payload or ExitRequest()).reason,
            exit_price=(payload or ExitRequest()).exit_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise upstream_service_error("broker", "exit_position", exc) from exc


@router.post("/exit-all")
async def exit_all_open_positions(
    request: Request,
    payload: ExitRequest | None = Body(default=None),
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    result = await exit_all_positions(
        db=db,
        actor=actor,
        request=request,
        execution_mode=execution_mode,
        reason=(payload or ExitRequest()).reason,
    )
    if execution_mode == "paper":
        from Backend.application.options.auto_paper_execution import exit_option_paper

        for position in _paper_options(execution_mode, "open"):
            result["checked"] += 1
            try:
                closed = exit_option_paper(position["option_order_id"], reason=(payload or ExitRequest()).reason)
                result["positions"].append({"position": _option_position(closed), "execution_mode": "paper"})
                result["exited"] += 1
            except Exception:
                result["errors"].append(f"{position['id']}: Option paper exit unavailable.")
    return result
