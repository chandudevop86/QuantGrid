from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from Backend.application.execution.execution_service import ExecutionService
from Backend.application.subscriptions import (
    SubscriptionAccess,
    subscription_access,
)
from Backend.core.database import get_db
from Backend.domain.engine.order_factory import ExecutionEngine
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.models import User
from Backend.presentation.api.roles import require_trade_execute

from .dependencies import (
    get_engine,
    _execution_mode,
)

router = APIRouter(
    prefix="/execution",
    tags=["Execution"],
)

service = ExecutionService()

def get_engine():
    return ExecutionEngine()
def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode

@router.post("/order")
async def place_order(
    signal: StrategySignal,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    return await service.execute(
        signal=signal,
        request=request,
        engine=engine,
        actor=actor,
        access=access,
        execution_mode=execution_mode,
        db=db,
    )