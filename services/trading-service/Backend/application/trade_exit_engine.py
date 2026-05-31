from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from Backend.application.candle_validation import get_market_session
from Backend.application.market_data_store import latest_candles
from Backend.application.position_store import close_open_position, get_position, list_open_positions
from Backend.domain.models.order import Order
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.infrastructure.broker.broker_client import BrokerClient, broker_client_for_mode


EXIT_REASONS = {
    "manual_exit",
    "stop_loss",
    "target",
    "trailing_stop_loss",
    "market_close",
}


@dataclass(slots=True)
class ExitDecision:
    should_exit: bool
    reason: str | None = None
    price: float | None = None
    details: dict[str, Any] | None = None


def exit_rules() -> dict[str, Any]:
    return {
        "stop_loss": True,
        "target": True,
        "trailing_stop_loss": {
            "enabled": _trailing_enabled(),
            "percent": _trailing_percent(),
            "source": "position.trailing_stop_loss or QUANTGRID_TRAILING_SL_PCT",
        },
        "manual_exit": True,
        "market_close": {
            "enabled": _market_close_exit_enabled(),
            "timezone": "Asia/Kolkata",
        },
    }


def evaluate_exit_rule(position: dict[str, Any], *, current_price: float | None = None, now: datetime | None = None) -> ExitDecision:
    price = float(current_price if current_price is not None else position.get("current_price") or _latest_price(str(position.get("symbol") or "")) or 0.0)
    if price <= 0:
        return ExitDecision(False, details={"reason": "price_unavailable"})

    side = str(position.get("side") or "").upper()
    stop_loss = float(position.get("stop_loss") or 0.0)
    target = float(position.get("target") or 0.0)

    if stop_loss and _price_crossed(side, price, stop_loss, trigger="stop"):
        return ExitDecision(True, "stop_loss", price, {"stop_loss": stop_loss})
    if target and _price_crossed(side, price, target, trigger="target"):
        return ExitDecision(True, "target", price, {"target": target})

    trailing_stop = _trailing_stop(position, price)
    if trailing_stop and _price_crossed(side, price, trailing_stop, trigger="stop"):
        return ExitDecision(True, "trailing_stop_loss", price, {"trailing_stop_loss": trailing_stop})

    if _market_close_exit_enabled() and not get_market_session(now).market_live:
        return ExitDecision(True, "market_close", price, {"market_status": get_market_session(now).status})

    return ExitDecision(False, price=price)


async def monitor_open_positions(
    *,
    db: Session,
    actor: User,
    request: Request | None = None,
    execution_mode: str = "paper",
    broker_client: BrokerClient | None = None,
) -> dict[str, Any]:
    positions = list_open_positions()
    exited: list[dict[str, Any]] = []
    errors: list[str] = []
    for position in positions:
        decision = evaluate_exit_rule(position)
        if not decision.should_exit:
            continue
        try:
            exited.append(
                await exit_position(
                    int(position["id"]),
                    db=db,
                    actor=actor,
                    request=request,
                    execution_mode=execution_mode,
                    reason=decision.reason or "rule_exit",
                    exit_price=decision.price,
                    broker_client=broker_client,
                )
            )
        except Exception as exc:
            errors.append(f"{position.get('id')}: {exc}")
    return {"checked": len(positions), "exited": len(exited), "positions": exited, "errors": errors}


async def exit_position(
    position_id: int,
    *,
    db: Session,
    actor: User,
    request: Request | None = None,
    execution_mode: str = "paper",
    reason: str = "manual_exit",
    exit_price: float | None = None,
    broker_client: BrokerClient | None = None,
) -> dict[str, Any]:
    normalized_reason = reason if reason in EXIT_REASONS else "manual_exit"
    position = get_position(position_id)
    if position is None:
        raise ValueError("position not found")
    if position.get("status") != "open":
        raise ValueError("position is not open")

    price = float(exit_price if exit_price is not None else _latest_price(str(position.get("symbol") or "")) or position.get("current_price") or position.get("entry_price") or 0.0)
    if price <= 0:
        raise ValueError("exit price is unavailable")

    broker_payload: dict[str, Any] | None = None
    if execution_mode == "live":
        client = broker_client or broker_client_for_mode("live")
        order = _exit_order(position, price)
        placed = await client.place_order(order)
        confirmed = await client.get_order_status(placed.broker_order_id)
        if not confirmed.confirmed or confirmed.status in {"rejected", "failed", "not_found"}:
            raise RuntimeError(f"broker exit not confirmed: {confirmed.status}")
        price = float(confirmed.price or price)
        broker_payload = confirmed.to_dict()

    closed = close_open_position(position_id, current_price=price, reason=normalized_reason)
    if closed is None:
        raise ValueError("position could not be closed")

    write_audit_log(
        db,
        action="position_exit",
        actor=actor,
        target_type="position",
        target_id=position_id,
        request=request,
        metadata={
            "status": "closed",
            "reason": normalized_reason,
            "execution_mode": execution_mode,
            "exit_price": price,
            "closed_pnl": closed.get("closed_pnl"),
            "broker_order_id": (broker_payload or {}).get("broker_order_id"),
            "broker_status": (broker_payload or {}).get("status"),
            "broker_response": broker_payload,
        },
    )
    return {"position": closed, "exit_reason": normalized_reason, "broker": broker_payload}


async def exit_all_positions(
    *,
    db: Session,
    actor: User,
    request: Request | None = None,
    execution_mode: str = "paper",
    reason: str = "manual_exit",
    broker_client: BrokerClient | None = None,
) -> dict[str, Any]:
    positions = list_open_positions()
    exited: list[dict[str, Any]] = []
    errors: list[str] = []
    for position in positions:
        try:
            exited.append(
                await exit_position(
                    int(position["id"]),
                    db=db,
                    actor=actor,
                    request=request,
                    execution_mode=execution_mode,
                    reason=reason,
                    broker_client=broker_client,
                )
            )
        except Exception as exc:
            errors.append(f"{position.get('id')}: {exc}")
    return {"checked": len(positions), "exited": len(exited), "positions": exited, "errors": errors}


def _exit_order(position: dict[str, Any], price: float) -> Order:
    side = "SELL" if str(position.get("side") or "").upper() == "BUY" else "BUY"
    return Order(
        symbol=str(position.get("symbol") or "").upper(),
        side=side,
        quantity=int(position.get("quantity") or 0),
        order_type="MARKET",
        price=price,
        metadata={
            "position_id": position.get("id"),
            "exit_for_broker_order_id": position.get("broker_order_id"),
            "correlation_id": f"EXIT-{position.get('id')}-{int(datetime.now(timezone.utc).timestamp())}",
        },
    )


def _price_crossed(side: str, price: float, trigger_price: float, *, trigger: str) -> bool:
    if side == "BUY":
        return price <= trigger_price if trigger == "stop" else price >= trigger_price
    return price >= trigger_price if trigger == "stop" else price <= trigger_price


def _latest_price(symbol: str) -> float | None:
    candles = latest_candles(symbol, "1m", 1)
    if not candles:
        return None
    try:
        price = float(candles[-1].get("close"))
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _trailing_enabled() -> bool:
    return os.getenv("QUANTGRID_TRAILING_SL_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def _trailing_percent() -> float:
    try:
        return float(os.getenv("QUANTGRID_TRAILING_SL_PCT", "0"))
    except ValueError:
        return 0.0


def _trailing_stop(position: dict[str, Any], price: float) -> float | None:
    explicit = position.get("trailing_stop_loss")
    if explicit not in {None, ""}:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            return None
    pct = _trailing_percent()
    if not _trailing_enabled() or pct <= 0:
        return None
    side = str(position.get("side") or "").upper()
    entry = float(position.get("entry_price") or price)
    if side == "BUY" and price > entry:
        return max(float(position.get("stop_loss") or 0.0), price * (1 - pct / 100))
    if side == "SELL" and price < entry:
        stop = price * (1 + pct / 100)
        configured = float(position.get("stop_loss") or 0.0)
        return min(configured, stop) if configured else stop
    return None


def _market_close_exit_enabled() -> bool:
    return os.getenv("QUANTGRID_MARKET_CLOSE_EXIT", "false").strip().lower() in {"1", "true", "yes"}
