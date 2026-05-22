import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from Backend.core.config import get_settings
from Backend.core.database import get_db
from Backend.application.notifications import alert_execution_event
from Backend.application.paper_trade_store import create_paper_trade
from Backend.application.risk_gate import evaluate_risk_gate
from Backend.application.signal_quality import decide_signal
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.execution_constraints import (
    apply_order_constraints,
    requested_quantity,
    validate_execution_constraints,
)
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.market_api import get_price
from Backend.application.market_data_store import latest_candles
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
        result = {
            "status": "no_trade",
            "symbol": signal.symbol,
            "reason": "Signal entry price is not aligned with market price.",
            "execution_mode": execution_mode,
            "source": "signal_based",
        }
        alert_execution_event(result)
        return result

    decision = decide_signal(
        signal,
        candles_1m=latest_candles(signal.symbol, "1m", 100),
        candles_15m=latest_candles(signal.symbol, "15m", 100),
    )
    gate = evaluate_risk_gate(decision)
    if not gate.allowed:
        write_audit_log(
            db,
            action="execution_blocked",
            actor=actor,
            target_type="symbol",
            target_id=signal.symbol,
            request=request,
            metadata={"reason": gate.reason, "decision": decision.to_dict()},
        )
        result = {
            "allowed": False,
            "status": "no_trade",
            "symbol": signal.symbol,
            "reason": gate.reason,
            "execution_mode": execution_mode,
            "source": "signal_based",
            "decision": decision.to_dict(),
        }
        alert_execution_event(result)
        return result

    constraints = validate_execution_constraints(signal)
    if not constraints.accepted:
        write_audit_log(
            db,
            action="execution_blocked",
            actor=actor,
            target_type="symbol",
            target_id=signal.symbol,
            request=request,
            metadata={
                "reason": constraints.reason,
                "requested_quantity": requested_quantity(signal),
                "rounded_quantity": constraints.quantity,
                "lot_size": constraints.lot_size,
                "required_margin": constraints.required_margin,
            },
        )
        result = {
            "status": "no_trade",
            "symbol": signal.symbol,
            "reason": constraints.reason,
            "execution_mode": execution_mode,
            "source": "signal_based",
            "lot_size": constraints.lot_size,
            "rounded_quantity": constraints.quantity,
            "required_margin": constraints.required_margin,
        }
        alert_execution_event(result)
        return result

    order = engine.order_from_signal(signal)
    order = apply_order_constraints(order, constraints, requested_quantity(signal))

    # simulate execution layer hook
    # - broker API
    # - DB save
    # - queue system

    result = {
        "allowed": True,
        "status": "paper_simulated",
        "execution_mode": execution_mode,
        "source": "signal_based",
        "decision": decision.to_dict(),
        "order": jsonable_encoder(order),
    }
    create_paper_trade(
        {
            "strategy": signal.strategy_name,
            "symbol": signal.symbol,
            "side": signal.side,
            "entry": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target": signal.target_price,
            "status": "paper_simulated",
            "pnl": 0.0,
            "reason": "OK",
            "score": decision.score,
            "regime": decision.regime,
            "signal_time": signal.signal_time.isoformat(),
        }
    )
    alert_execution_event(result)
    return result
