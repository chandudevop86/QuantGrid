from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from Backend.application.candle_validation import validate_live_candle
from Backend.application.dto import serialize_signal
from Backend.core.config import get_settings
from Backend.core.database import get_db
from Backend.application.notifications import alert_execution_event
from Backend.application.paper_trade_store import create_paper_trade
from Backend.application.risk_gate import evaluate_risk_gate
from Backend.application.signal_quality import decide_signal
from Backend.application.signal_validation import diagnose_signal_run, validate_signals
from Backend.application.trading_service import TradingService
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.execution_constraints import (
    apply_order_constraints,
    requested_quantity,
    validate_execution_constraints,
)
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.market_api import get_candles, get_price
from Backend.application.market_data_store import latest_candles
from Backend.application.monitoring import observe_paper_order, observe_rejected_order, observe_signal_generation
from Backend.presentation.api.roles import require_roles, require_trade_execute

router = APIRouter()
AUTO_SCAN_STRATEGIES = ["amd", "breakout", "btst", "mean_reversion", "mtf", "supply_demand"]


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
    if price_response.get("source") != "yahoo-finance":
        return False
    market_price = price_response.get("price")
    if market_price is None or float(market_price) <= 0:
        return False
    return abs(float(signal.entry_price) - float(market_price)) / float(market_price) <= 0.02


class AutoPaperExecutionRequest(BaseModel):
    symbol: str = "NIFTY"
    interval: str = "1m"
    period: str = "1d"
    capital: float = Field(default=100000, gt=0)
    risk_pct: float = Field(default=1, gt=0)
    rr_ratio: float = Field(default=2, gt=0)
    strategies: list[str] | None = None


def _paper_response(
    *,
    status_value: str,
    symbol: str,
    strategy: str | None,
    signal: StrategySignal | None,
    reason: str,
    execution_mode: str,
    strategy_diagnostics: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": status_value,
        "symbol": symbol.upper(),
        "strategy": strategy,
        "signal": signal.side if signal else None,
        "entry": float(signal.entry_price) if signal else None,
        "stop": float(signal.stop_loss) if signal else None,
        "target": float(signal.target_price) if signal else None,
        "reason": reason,
        "execution_mode": execution_mode,
        "strategy_diagnostics": strategy_diagnostics or {},
    }
    if extra:
        response.update(extra)
    return response


def _audit_execution_result(
    db: Session,
    request: Request,
    actor: User,
    result: dict[str, Any],
) -> None:
    submitted = result.get("status") == "paper_order_submitted"
    write_audit_log(
        db,
        action="paper_order_submitted" if submitted else "execution_blocked",
        actor=actor,
        target_type="symbol",
        target_id=result.get("symbol"),
        request=request,
        metadata={
            "strategy": result.get("strategy"),
            "side": result.get("signal"),
            "reason": result.get("reason"),
            "status": "submitted" if submitted else "rejected",
        },
    )


def _trade_shape_reason(signal: StrategySignal) -> str | None:
    try:
        entry = float(signal.entry_price)
        stop = float(signal.stop_loss)
        target = float(signal.target_price)
    except (TypeError, ValueError):
        return "Entry, stop, and target must be numeric."
    side = str(signal.side or "").upper()
    if side not in {"BUY", "SELL"}:
        return "Signal side must be BUY or SELL."
    if entry <= 0 or stop <= 0 or target <= 0:
        return "Entry, stop, and target must be positive."
    if side == "BUY" and not stop < entry < target:
        return "BUY signal requires stop < entry < target."
    if side == "SELL" and not target < entry < stop:
        return "SELL signal requires target < entry < stop."
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0 or reward <= 0:
        return "Risk/reward is invalid."
    return None


def _strategy_candles(candles_response: dict[str, Any]) -> list[dict[str, Any]]:
    candles = list(candles_response.get("candles", []))
    if candles_response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


def _submit_paper_signal(
    signal: StrategySignal,
    *,
    engine: ExecutionEngine,
    execution_mode: str,
    candles_1m: list[dict[str, Any]] | None = None,
    candles_15m: list[dict[str, Any]] | None = None,
    strategy_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if execution_mode != "paper":
        observe_rejected_order("paper_mode_required", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason="Paper execution requires X-QuantGrid-Mode: paper.",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
        )

    shape_reason = _trade_shape_reason(signal)
    if shape_reason:
        observe_rejected_order(shape_reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=shape_reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
        )

    candles_1m = candles_1m if candles_1m is not None else latest_candles(signal.symbol, "1m", 100)
    candles_15m = candles_15m if candles_15m is not None else latest_candles(signal.symbol, "15m", 100)
    if not candles_1m:
        try:
            candles_1m = _strategy_candles(get_candles(signal.symbol, interval="1m", period="1d", limit=100))
        except Exception:
            candles_1m = []
    if not candles_15m:
        try:
            candles_15m = _strategy_candles(get_candles(signal.symbol, interval="15m", period="1d", limit=100))
        except Exception:
            candles_15m = []
    candle_validation = validate_live_candle(candles_1m, interval="1m", mode="paper")
    if not candle_validation.valid_for_execution:
        observe_rejected_order(f"MARKET_NOT_LIVE_FOR_EXECUTION: {candle_validation.market_status}", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=f"MARKET_NOT_LIVE_FOR_EXECUTION: {candle_validation.market_status}",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={"allowed": False, "validation": candle_validation.model_dump()},
        )
    decision = decide_signal(signal, candles_1m=candles_1m, candles_15m=candles_15m)
    gate = evaluate_risk_gate(decision)
    if not gate.allowed:
        observe_rejected_order(gate.reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=gate.reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={"allowed": False, "decision": decision.to_dict()},
        )

    if not _market_aligned(signal):
        observe_rejected_order("market_alignment_failed", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason="Signal entry price is not aligned with market price.",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={"allowed": False, "decision": decision.to_dict()},
        )

    constraints = validate_execution_constraints(signal)
    if not constraints.accepted:
        observe_rejected_order(constraints.reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=constraints.reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={
                "allowed": False,
                "decision": decision.to_dict(),
                "lot_size": constraints.lot_size,
                "rounded_quantity": constraints.quantity,
                "required_margin": constraints.required_margin,
            },
        )

    order = apply_order_constraints(
        engine.order_from_signal(signal),
        constraints,
        requested_quantity(signal),
    )
    result = _paper_response(
        status_value="paper_order_submitted",
        symbol=signal.symbol,
        strategy=signal.strategy_name,
        signal=signal,
        reason="OK",
        execution_mode=execution_mode,
        strategy_diagnostics=strategy_diagnostics,
        extra={
            "allowed": True,
            "source": "signal_based",
            "decision": decision.to_dict(),
            "order": jsonable_encoder(order),
        },
    )
    create_paper_trade(
        {
            "strategy": signal.strategy_name,
            "symbol": signal.symbol,
            "side": signal.side,
            "entry": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target": signal.target_price,
            "status": "paper_order_submitted",
            "pnl": 0.0,
            "reason": "OK",
            "score": decision.score,
            "regime": decision.regime,
            "signal_time": signal.signal_time.isoformat(),
        }
    )
    observe_paper_order("paper_order_submitted", signal.strategy_name, signal.symbol)
    return result


@router.post("/auto-paper")
async def auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    symbol = payload.symbol.upper()
    write_audit_log(
        db,
        action="paper_auto_scan_triggered",
        actor=actor,
        target_type="symbol",
        target_id=symbol,
        request=request,
        metadata={"mode": execution_mode},
    )

    if execution_mode != "paper":
        return _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason="Auto execution is paper-only.",
            execution_mode=execution_mode,
        )

    candles_response = get_candles(symbol, interval=payload.interval, period=payload.period, limit=150)
    confirmation_response = get_candles(symbol, interval="5m", period=payload.period, limit=150)
    trend_response = get_candles(symbol, interval="15m", period=payload.period, limit=150)
    candles = _strategy_candles(candles_response)
    confirmation_candles = _strategy_candles(confirmation_response)
    trend_candles = _strategy_candles(trend_response)
    candle_validation = validate_live_candle(
        candles,
        interval=payload.interval,
        mode="paper",
        source=candles_response.get("source"),
        provider_fetched_at=candles_response.get("fetched_at"),
    )
    service = TradingService()
    strategies = payload.strategies or AUTO_SCAN_STRATEGIES
    strategy_diagnostics: dict[str, Any] = {}

    for strategy in strategies:
        try:
            raw_signals = service.run_strategy(
                strategy_name=strategy,
                data=candles,
                symbol=symbol,
                capital=payload.capital,
                risk_pct=payload.risk_pct,
                rr_ratio=payload.rr_ratio,
                params={"mtf_candles": confirmation_candles, "htf_candles": trend_candles},
            )
            observe_signal_generation(strategy, "success")
            validated_signals, data_source = validate_signals(
                raw_signals,
                symbol=symbol,
                candles=candles,
                candle_source=candles_response.get("source"),
            )
            diagnostics = diagnose_signal_run(
                raw_signals,
                symbol=symbol,
                candles=candles,
                candle_source=candles_response.get("source"),
            )
            strategy_diagnostics[strategy] = {
                "raw_signals": len(raw_signals),
                "validated_signals": len(validated_signals),
                "data_source": data_source,
                "market_status": candle_validation.market_status,
                "validation": candle_validation.model_dump(),
                "diagnostics": diagnostics,
            }
            if not validated_signals:
                continue

            selected = validated_signals[0]
            strategy_diagnostics[strategy]["selected_signal"] = serialize_signal(selected)
        except Exception as exc:
            observe_signal_generation(strategy, "error")
            strategy_diagnostics[strategy] = {
                "raw_signals": 0,
                "validated_signals": 0,
                "market_status": candle_validation.market_status,
                "validation": candle_validation.model_dump(),
                "diagnostics": [f"Strategy scan failed: {exc}"],
            }
            continue

        selected = validated_signals[0]
        strategy_diagnostics[strategy]["selected_signal"] = serialize_signal(selected)
        result = _submit_paper_signal(
            selected,
            engine=engine,
            execution_mode=execution_mode,
            candles_1m=candles,
            candles_15m=trend_candles,
            strategy_diagnostics=strategy_diagnostics,
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    result = _paper_response(
        status_value="no_trade",
        symbol=symbol,
        strategy=None,
        signal=None,
        reason="No validated signal found across auto-scan strategies.",
        execution_mode=execution_mode,
        strategy_diagnostics=strategy_diagnostics,
        extra={
            "candles_analyzed": len(candles),
            "strategies_checked": strategies,
            "validation": candle_validation.model_dump(),
        },
    )
    alert_execution_event(result)
    return result


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
        if not settings.risk_configured:
            write_audit_log(
                db,
                action="execution_blocked",
                actor=actor,
                target_type="symbol",
                target_id=signal.symbol,
                request=request,
                metadata={"reason": "risk_config_missing"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Live trading requires risk config: QUANTGRID_CAPITAL, QUANTGRID_RISK_PER_TRADE_PCT, and QUANTGRID_MAX_DAILY_LOSS.",
            )
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

    result = _submit_paper_signal(signal, engine=engine, execution_mode=execution_mode)
    _audit_execution_result(db, request, actor, result)
    alert_execution_event(result)
    return result
