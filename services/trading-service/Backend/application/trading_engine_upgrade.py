from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from Backend.application.kill_switch import kill_switch_status
from Backend.application.paper_trade_store import create_paper_trade, list_paper_trades
from Backend.application.position_store import (
    create_open_position,
    get_position,
    list_open_positions,
    position_summary,
    update_open_position,
)
from Backend.application.trade_exit_engine import exit_rules


VALID_SIDES = {"BUY", "SELL"}
VALID_SCALE_ACTIONS = {"scale_in", "scale_out"}


def trading_engine_dashboard() -> dict[str, Any]:
    halt = kill_switch_status()
    positions = list_open_positions()
    return {
        "module": "trading_engine",
        "generated_at": _now(),
        "state": "halted" if halt.get("active") else "paper_ready",
        "capabilities": {
            "stop_loss": True,
            "trailing_stop_loss": True,
            "target": True,
            "scale_in": "paper",
            "scale_out": "paper",
            "basket_orders": "paper",
            "paper_execution_logs": True,
            "kill_switch": True,
            "audit_trail": True,
        },
        "guardrails": {
            "paper_only_new_workflows": True,
            "live_basket_rejected": True,
            "live_scale_rejected": True,
            "kill_switch_active": bool(halt.get("active")),
            "kill_switch_reason": halt.get("reason"),
            "requires_stop_and_target": True,
        },
        "exit_rules": exit_rules(),
        "summary": position_summary(),
        "open_positions": positions,
        "paper_execution_logs": list_paper_trades(50),
        "kill_switch": halt,
    }


def submit_paper_basket(*, legs: list[dict[str, Any]], execution_mode: str = "paper", reason: str | None = None) -> dict[str, Any]:
    if execution_mode != "paper":
        raise ValueError("Basket orders are paper-only until broker-native basket guardrails are implemented.")
    _ensure_trading_allowed()
    if not legs:
        raise ValueError("Basket requires at least one leg.")

    basket_id = f"BASKET-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    created: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, leg in enumerate(legs, start=1):
        try:
            normalized = _normalize_leg(leg)
            broker_order_id = f"{basket_id}-{index}"
            trade = create_paper_trade(
                {
                    **normalized,
                    "status": "paper_basket_submitted",
                    "reason": reason or "paper basket order",
                    "broker_order_id": broker_order_id,
                    "raw_safe_broker_response": {"basket_id": basket_id, "leg_index": index},
                }
            )
            position = create_open_position(
                {
                    **normalized,
                    "entry_price": normalized["entry"],
                    "target_price": normalized["target"],
                    "current_price": normalized["entry"],
                    "broker_order_id": broker_order_id,
                }
            )
            created.append({"leg_index": index, "trade": trade, "position": position})
        except Exception as exc:
            errors.append(f"leg {index}: {exc}")

    if not created:
        raise ValueError("; ".join(errors) or "Basket could not be created.")

    return {
        "status": "paper_basket_submitted" if not errors else "paper_basket_partially_submitted",
        "basket_id": basket_id,
        "created_count": len(created),
        "error_count": len(errors),
        "legs": created,
        "errors": errors,
        "execution_mode": execution_mode,
        "reason": reason or "paper basket order",
    }


def scale_position(
    position_id: int,
    *,
    action: str,
    quantity: int,
    price: float | None = None,
    reason: str | None = None,
    execution_mode: str = "paper",
) -> dict[str, Any]:
    if execution_mode != "paper":
        raise ValueError("Scale-in and scale-out are paper-only until broker confirmations are implemented.")
    _ensure_trading_allowed()
    normalized_action = action.strip().lower()
    if normalized_action not in VALID_SCALE_ACTIONS:
        raise ValueError("Scale action must be scale_in or scale_out.")
    if quantity <= 0:
        raise ValueError("Scale quantity must be greater than zero.")

    position = get_position(position_id)
    if position is None or position.get("status") != "open":
        raise ValueError("Open position not found.")

    old_quantity = int(position.get("quantity") or 0)
    if old_quantity <= 0:
        raise ValueError("Open position quantity is invalid.")
    execution_price = float(price if price is not None else position.get("current_price") or position.get("entry_price") or 0.0)
    if execution_price <= 0:
        raise ValueError("Scale price must be greater than zero.")

    side = str(position.get("side") or "").upper()
    if normalized_action == "scale_in":
        new_quantity = old_quantity + quantity
        old_entry = float(position.get("entry_price") or execution_price)
        weighted_entry = ((old_entry * old_quantity) + (execution_price * quantity)) / new_quantity
        updated = update_open_position(
            position_id,
            {"quantity": new_quantity, "entry_price": round(weighted_entry, 4), "current_price": execution_price},
        )
        pnl = 0.0
    else:
        close_quantity = min(quantity, old_quantity)
        new_quantity = old_quantity - close_quantity
        pnl = _pnl(side, close_quantity, float(position.get("entry_price") or execution_price), execution_price)
        updated = update_open_position(position_id, {"quantity": new_quantity, "current_price": execution_price}) if new_quantity else None

    paper_log = create_paper_trade(
        {
            "strategy": f"position_{normalized_action}",
            "symbol": position.get("symbol"),
            "side": side,
            "entry": execution_price,
            "stop_loss": position.get("stop_loss"),
            "target": position.get("target"),
            "trailing_stop_loss": position.get("trailing_stop_loss"),
            "trailing_stop_pct": position.get("trailing_stop_pct"),
            "status": normalized_action,
            "pnl": pnl,
            "reason": reason or normalized_action.replace("_", " "),
            "broker_order_id": f"SCALE-{position_id}-{uuid4().hex[:8]}",
            "raw_safe_broker_response": {
                "position_id": position_id,
                "action": normalized_action,
                "old_quantity": old_quantity,
                "requested_quantity": quantity,
                "new_quantity": new_quantity,
                "execution_mode": execution_mode,
            },
        }
    )

    return {
        "status": normalized_action,
        "position_id": position_id,
        "old_quantity": old_quantity,
        "new_quantity": new_quantity,
        "price": execution_price,
        "realized_pnl": round(pnl, 2),
        "position": updated,
        "paper_log": paper_log,
        "execution_mode": execution_mode,
    }


def _ensure_trading_allowed() -> None:
    halt = kill_switch_status()
    if halt.get("active"):
        raise ValueError(f"KILL_SWITCH_ACTIVE: {halt.get('reason') or 'Trading halted'}")


def _normalize_leg(leg: dict[str, Any]) -> dict[str, Any]:
    symbol = str(leg.get("symbol") or "").upper().strip()
    side = str(leg.get("side") or "").upper().strip()
    quantity = int(leg.get("quantity") or 0)
    entry = float(leg.get("entry") or leg.get("entry_price") or 0.0)
    stop = float(leg.get("stop_loss") or 0.0)
    target = float(leg.get("target") or leg.get("target_price") or 0.0)
    if not symbol:
        raise ValueError("symbol is required")
    if side not in VALID_SIDES:
        raise ValueError("side must be BUY or SELL")
    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")
    if entry <= 0 or stop <= 0 or target <= 0:
        raise ValueError("entry, stop_loss, and target must be greater than zero")
    if side == "BUY" and not (stop < entry < target):
        raise ValueError("BUY leg requires stop_loss below entry and target above entry")
    if side == "SELL" and not (target < entry < stop):
        raise ValueError("SELL leg requires target below entry and stop_loss above entry")
    return {
        "strategy": str(leg.get("strategy") or leg.get("strategy_name") or "manual_basket"),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "trailing_stop_loss": leg.get("trailing_stop_loss"),
        "trailing_stop_pct": leg.get("trailing_stop_pct"),
        "score": float(leg.get("score") or 0.0),
    }


def _pnl(side: str, quantity: int, entry: float, price: float) -> float:
    if side == "SELL":
        return round((entry - price) * quantity, 2)
    return round((price - entry) * quantity, 2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
