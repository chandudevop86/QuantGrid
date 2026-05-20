import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from Backend.core.config import get_settings
from Backend.core.database import get_db
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.market_api import get_price
from Backend.presentation.api.roles import require_roles, require_trade_execute

router = APIRouter()


# dependency injection (cleaner + testable)
def get_engine():
    return ExecutionEngine()


def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode


def _market_aligned(signal: StrategySignal) -> bool:
    price_response = get_price(signal.symbol)
    market_price = price_response.get("price")
    if market_price is None or float(market_price) <= 0:
        return False
    return abs(float(signal.entry_price) - float(market_price)) / float(market_price) <= 0.02


@router.post("/order")
async def place_order(
    signal: StrategySignal,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    write_audit_log(
        db,
        action="execution_triggered",
        actor=actor,
        target_type="symbol",
        target_id=signal.symbol,
        request=request,
        metadata={"mode": execution_mode, "strategy": signal.strategy_name},
    )

    if execution_mode == "live":
        settings = get_settings()
        if not settings.live_trading_enabled:
            write_audit_log(
                db,
                action="execution_blocked",
                actor=actor,
                target_type="symbol",
                target_id=signal.symbol,
                request=request,
                metadata={"reason": "live_trading_disabled"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Live trading is disabled. Paper trading only.")
        if not settings.broker_configured:
            write_audit_log(
                db,
                action="execution_blocked",
                actor=actor,
                target_type="symbol",
                target_id=signal.symbol,
                request=request,
                metadata={"reason": "broker_not_configured"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Live trading requires broker credentials.")
        write_audit_log(
            db,
            action="execution_blocked",
            actor=actor,
            target_type="symbol",
            target_id=signal.symbol,
            request=request,
            metadata={"reason": "live_execution_not_implemented"},
        )
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Live broker execution is not implemented.")

    if not _market_aligned(signal):
        write_audit_log(
            db,
            action="execution_blocked",
            actor=actor,
            target_type="symbol",
            target_id=signal.symbol,
            request=request,
            metadata={"reason": "market_alignment_failed"},
        )
        return {
            "status": "no_trade",
            "reason": "Signal entry price is not aligned with market price.",
            "source": "signal_based",
        }

    order = engine.order_from_signal(signal)

    # simulate execution layer hook
    # - broker API
    # - DB save
    # - queue system

    return {
        "status": "paper_simulated",
        "execution_mode": execution_mode,
        "source": "signal_based",
        "order": jsonable_encoder(order),
    }
