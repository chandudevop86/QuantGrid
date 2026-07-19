from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from Backend.application.paper_trade_store import DATA_DIR, list_paper_trades, update_paper_trade_status
from Backend.application.order_store import broker_status_to_order_status, list_orders, transition_order
from Backend.application.position_store import (
    close_open_position,
    create_open_position,
    find_position_by_broker_order_id,
    list_open_positions,
    update_open_position,
)
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import AuditLog, User
from Backend.infrastructure.broker.broker_client import BrokerClient, BrokerOrderResult


STATUS_FILE = DATA_DIR / "broker_reconciliation_status.json"
SUBMITTED_STATUSES = {"paper_order_submitted", "live_order_submitted", "submitted", "broker_submitted", "pending", "confirmed", "open", "filled"}
REJECTED_STATUSES = {"rejected", "failed", "cancelled", "expired", "not_found"}
FILLED_STATUSES = {"filled", "traded", "complete", "completed", "confirmed"}
OPEN_STATUSES = {"open", "pending", "transit", "confirmed"}
PRE_BROKER_STALE_STATUSES = {"requested", "risk_approved"}
AMBIGUOUS_NO_BROKER_ID_STATUSES = {"broker_submitted", "pending", "open", "partially_filled"}
STALE_LOCAL_ORDER_MINUTES = 30


async def reconcile_broker_state(
    *,
    db: Session,
    broker_client: BrokerClient,
    actor: User,
    request: Request | None = None,
) -> dict[str, Any]:
    summary : dict[str, Any] = {
        "checked_orders": 0,
        "checked_positions": 0,
        "mismatches": 0,
        "fixed": 0,
        "needs_review": 0,
        "errors": [],
    }
    _recover_stale_local_orders(summary, db, actor, request)
    local_orders = _local_orders(db)
    

    try:
        broker_positions = await broker_client.get_positions()
        broker_positions_available = True
    except Exception as exc:
        summary["errors"].append(f"broker positions unavailable: {exc}")
        broker_positions = []
        broker_positions_available = False

    broker_position_index = _broker_position_index(broker_positions)

    for local_order in local_orders:
        broker_order_id = str(local_order.get("broker_order_id") or "")
        if not broker_order_id:
            continue
        summary["checked_orders"] += 1
        try:
            broker_order = await broker_client.get_order_status(broker_order_id)
        except Exception as exc:
            summary["errors"].append(f"{broker_order_id}: broker order unavailable: {exc}")
            continue

        order_status = _normal_status(broker_order.status)
        position = find_position_by_broker_order_id(broker_order_id)

        if order_status == "not_found":
            _record_fix(
                summary,
                db,
                actor,
                request,
                "missing_broker_order",
                broker_order_id,
                {"local_order": local_order, "broker_status": broker_order.to_dict()},
            )
            update_paper_trade_status(
                broker_order_id,
                status="broker_missing",
                reason="Broker order was not found during reconciliation.",
                broker_status=broker_order.status,
                raw_safe_broker_response=broker_order.metadata.get("raw_safe"),
            )
            _transition_local_order_if_present(
                local_order,
                "rejected",
                status_reason="Broker order was not found during reconciliation.",
                broker_status=broker_order.status,
            )
            if position and position.get("status") == "open":
                close_open_position(int(position["id"]), reason="missing_broker_order")
            continue

        if local_order.get("status") in SUBMITTED_STATUSES and order_status in REJECTED_STATUSES:
            _record_fix(
                summary,
                db,
                actor,
                request,
                "local_submitted_broker_rejected",
                broker_order_id,
                {"local_order": local_order, "broker_status": broker_order.to_dict()},
            )
            update_paper_trade_status(
                broker_order_id,
                status=f"broker_{order_status}",
                reason=f"Broker status is {order_status}.",
                broker_status=broker_order.status,
                raw_safe_broker_response=broker_order.metadata.get("raw_safe"),
            )
            _transition_local_order_if_present(
                local_order,
                broker_status_to_order_status(broker_order.status, confirmed=broker_order.confirmed),
                status_reason=f"Broker status is {order_status}.",
                broker_status=broker_order.status,
                entry_price=broker_order.price,
            )
            if position and position.get("status") == "open":
                close_open_position(int(position["id"]), current_price=broker_order.price, reason=f"broker_{order_status}")
            continue

        if order_status in FILLED_STATUSES and local_order.get("local_order_id") and _normal_status(local_order.get("status")) != "filled":
            _record_fix(
                summary,
                db,
                actor,
                request,
                "broker_filled_local_order_not_updated",
                broker_order_id,
                {"local_order": local_order, "broker_status": broker_order.to_dict()},
            )
            _transition_local_order_if_present(
                local_order,
                "filled",
                status_reason="Broker confirmed fill during reconciliation.",
                broker_status=broker_order.status,
                entry_price=broker_order.price,
            )

        if order_status in FILLED_STATUSES and not position:
            _record_fix(
                summary,
                db,
                actor,
                request,
                "broker_filled_local_position_missing",
                broker_order_id,
                {"local_order": local_order, "broker_status": broker_order.to_dict()},
            )
            create_open_position(_position_payload_from_order(broker_order, local_order))
            continue

        if position:
            _fix_position_differences(summary, db, actor, request, position, broker_order, broker_position_index)

    open_positions = list_open_positions()
    summary["checked_positions"] = len(open_positions) + len(broker_positions)
    if not broker_positions_available:
        _write_status(summary)
        return summary

    local_position_keys = {
        _position_key(str(position.get("symbol") or ""), str(position.get("side") or ""))
        for position in open_positions
    }
    for key, broker_position_item in broker_position_index.items():
        if int(broker_position_item.get("quantity") or 0) <= 0 or key in local_position_keys:
            continue

        _record_review(
            summary,
            db,
            actor,
            request,
            "broker_position_local_missing",
            key,
            {"broker_position": broker_position_item},
        )
    for position in open_positions:
        broker_order_id = str(position.get("broker_order_id") or "")

        matched_broker_position: dict[str, Any] | None = _matching_broker_position(
                position,
                broker_position_index,
            )

        if matched_broker_position and int(matched_broker_position["quantity"]) > 0:
            continue

        broker_order: BrokerOrderResult | None = None

        if broker_order_id:
            try:
                broker_order = await broker_client.get_order_status(broker_order_id)
            except Exception:
                broker_order = None

        if (
            broker_order
            and _normal_status(broker_order.status) in OPEN_STATUSES | FILLED_STATUSES
        ):
            pass
        
        if position is None:
            continue

    _record_fix(
        summary,
        db,
        actor,
        request,
        "closed_position_still_marked_open",
        broker_order_id or position.get("symbol") or "-",
        {
            "local_position": position,
            "broker_position": matched_broker_position,
        },
    )

    close_open_position(
        int(position["id"]),
        current_price=(matched_broker_position or {}).get("price"),
        reason="broker_position_closed",
    )

    _write_status(summary)
    return summary



def reconciliation_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {
            "last_run_at": None,
            "checked_orders": 0,
            "checked_positions": 0,
            "mismatches": 0,
            "fixed": 0,
            "needs_review": 0,
            "errors": [],
        }

    try:
        payload = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {
            "last_run_at": None,
            "checked_orders": 0,
            "checked_positions": 0,
            "mismatches": 0,
            "fixed": 0,
            "needs_review": 0,
            "errors": ["reconciliation status file is unreadable"],
        }

def _recover_stale_local_orders(
    summary: dict[str, Any],
    db: Session,
    actor: User,
    request: Request | None,
) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_LOCAL_ORDER_MINUTES)
    for order in list_orders(500):
        status = _normal_status(order.get("status"))
        if status not in PRE_BROKER_STALE_STATUSES | AMBIGUOUS_NO_BROKER_ID_STATUSES:
            continue
        if order.get("broker_order_id"):
            continue
        updated_at = _parse_time(order.get("updated_at") or order.get("created_at"))
        if updated_at is None or updated_at > cutoff:
            continue
        if status in PRE_BROKER_STALE_STATUSES:
            _record_fix(
                summary,
                db,
                actor,
                request,
                "stale_pre_broker_order_failed",
                order.get("local_order_id") or "-",
                {"local_order": order, "stale_minutes": STALE_LOCAL_ORDER_MINUTES},
            )
            transition_order(
                str(order["local_order_id"]),
                "failed",
                status_reason="Stale pre-broker lifecycle order recovered after restart.",
                broker_status="not_submitted",
            )
            continue
        _record_review(
            summary,
            db,
            actor,
            request,
            "ambiguous_broker_submission_missing_id",
            order.get("local_order_id") or "-",
            {"local_order": order, "stale_minutes": STALE_LOCAL_ORDER_MINUTES},
        )
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "last_run_at": None,
            "checked_orders": 0,
            "checked_positions": 0,
            "mismatches": 0,
            "fixed": 0,
            "needs_review": 0,
            "errors": ["reconciliation status file is unreadable"],
        }


def _local_orders(db: Session) -> list[dict[str, Any]]:
    orders: dict[str, dict[str, Any]] = {}
    positions_by_order = {
        str(position.get("broker_order_id")): position
        for position in list_open_positions()
        if position.get("broker_order_id")
    }
    for order in list_orders(500):
        broker_order_id = order.get("broker_order_id")
        if not broker_order_id:
            continue
        orders[str(broker_order_id)] = {
            "source": "orders",
            "local_order_id": order.get("local_order_id"),
            "broker_order_id": str(broker_order_id),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "quantity": order.get("quantity"),
            "price": order.get("entry_price"),
            "status": order.get("status"),
            "raw": order,
        }
    for trade in list_paper_trades(500):
        broker_order_id = trade.get("broker_order_id")
        if not broker_order_id:
            continue
        if str(broker_order_id) in orders:
            continue
        orders[str(broker_order_id)] = {
            "source": "paper_trades",
            "broker_order_id": str(broker_order_id),
            "symbol": trade.get("symbol"),
            "side": trade.get("side"),
            "price": trade.get("entry"),
            "status": trade.get("status"),
            "raw": trade,
        }

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["paper_order_submitted", "live_order_submitted"]))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(500)
        .all()
    )
    for row in rows:
        metadata = _metadata(row.metadata_json)
        broker_order_id = metadata.get("broker_order_id")
        if not broker_order_id or str(broker_order_id) in orders:
            continue
        broker_order = metadata.get("broker_order") if isinstance(metadata.get("broker_order"), dict) else {}
        orders[str(broker_order_id)] = {
            "source": "audit_logs",
            "broker_order_id": str(broker_order_id),
            "symbol": row.target_id or broker_order.get("symbol"),
            "side": broker_order.get("side") or metadata.get("side"),
            "price": broker_order.get("price"),
            "status": metadata.get("status") or row.status,
            "raw": {"audit_id": row.id, "metadata": metadata},
        }

    for broker_order_id, position in positions_by_order.items():
        orders.setdefault(
            broker_order_id,
            {
                "source": "positions",
                "broker_order_id": broker_order_id,
                "symbol": position.get("symbol"),
                "side": position.get("side"),
                "price": position.get("entry_price"),
                "status": position.get("status"),
                "raw": position,
            },
        )
        orders[broker_order_id]["quantity"] = position.get("quantity")
    return list(orders.values())


def _transition_local_order_if_present(
    local_order: dict[str, Any],
    status: str,
    *,
    status_reason: str,
    broker_status: str | None = None,
    entry_price: float | None = None,
) -> None:
    local_order_id = local_order.get("local_order_id")
    if not local_order_id:
        return
    transition_order(
        str(local_order_id),
        status,
        status_reason=status_reason,
        broker_order_id=local_order.get("broker_order_id"),
        broker_status=broker_status,
        entry_price=entry_price,
    )


def _fix_position_differences(
    summary: dict[str, Any],
    db: Session,
    actor: User,
    request: Request | None,
    position: dict[str, Any],
    broker_order: BrokerOrderResult,
    broker_position_index: dict[str, dict[str, Any]],
) -> None:
    broker_position = _matching_broker_position(position, broker_position_index)
    expected_quantity = int((broker_position or {}).get("quantity") or broker_order.quantity or 0)
    expected_price = float((broker_position or {}).get("price") or broker_order.price or position.get("entry_price") or 0.0)
    changes: dict[str, Any] = {}
    quantity_changed = bool(expected_quantity and int(position.get("quantity") or 0) != expected_quantity)
    if quantity_changed:
        changes["quantity"] = expected_quantity
    if expected_price and abs(float(position.get("entry_price") or 0.0) - expected_price) > 0.01:
        changes["entry_price"] = expected_price
        changes["current_price"] = expected_price
    if not changes:
        return
    mismatch_type = "quantity_mismatch" if "quantity" in changes else "price_mismatch"
    if "quantity" in changes and "entry_price" in changes:
        mismatch_type = "quantity_price_mismatch"
    if quantity_changed:
        _record_review(
            summary,
            db,
            actor,
            request,
            mismatch_type,
            position.get("broker_order_id") or broker_order.broker_order_id,
            {"local_position": position, "broker_order": broker_order.to_dict(), "broker_position": broker_position, "changes": changes},
        )
        return
    _record_fix(
        summary,
        db,
        actor,
        request,
        mismatch_type,
        position.get("broker_order_id") or broker_order.broker_order_id,
        {"local_position": position, "broker_order": broker_order.to_dict(), "broker_position": broker_position, "changes": changes},
    )
    update_open_position(int(position["id"]), changes)


def _record_review(
    summary: dict[str, Any],
    db: Session,
    actor: User,
    request: Request | None,
    mismatch_type: str,
    target_id: Any,
    metadata: dict[str, Any],
) -> None:
    summary["mismatches"] += 1
    summary["needs_review"] += 1
    write_audit_log(
        db,
        action="broker_reconciliation_change",
        actor=actor,
        target_type="broker_order",
        target_id=target_id,
        request=request,
        metadata={
            "status": "needs_review",
            "reason": mismatch_type,
            "mismatch_type": mismatch_type,
            **metadata,
        },
    )


def _record_fix(
    summary: dict[str, Any],
    db: Session,
    actor: User,
    request: Request | None,
    mismatch_type: str,
    target_id: Any,
    metadata: dict[str, Any],
) -> None:
    summary["mismatches"] += 1
    summary["fixed"] += 1
    write_audit_log(
        db,
        action="broker_reconciliation_change",
        actor=actor,
        target_type="broker_order",
        target_id=target_id,
        request=request,
        metadata={
            "status": "fixed",
            "reason": mismatch_type,
            "mismatch_type": mismatch_type,
            **metadata,
        },
    )


def _position_payload_from_order(broker_order: BrokerOrderResult, local_order: dict[str, Any]) -> dict[str, Any]:
    price = broker_order.price or local_order.get("price") or 0.0
    return {
        "broker_order_id": broker_order.broker_order_id,
        "symbol": broker_order.symbol or local_order.get("symbol"),
        "side": broker_order.side or local_order.get("side"),
        "quantity": broker_order.quantity or local_order.get("quantity") or 0,
        "entry_price": price,
        "stop_loss": 0.0,
        "target": 0.0,
        "current_price": price,
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }


def _broker_position_index(positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for raw in positions:
        normalized = _normalize_broker_position(raw)
        if not normalized["symbol"]:
            continue
        index[_position_key(normalized["symbol"], normalized["side"])] = normalized
    return index


def _matching_broker_position(position: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return index.get(_position_key(str(position.get("symbol") or ""), str(position.get("side") or "")))


def _normalize_broker_position(raw: dict[str, Any]) -> dict[str, Any]:
    quantity = _first_number(raw, ["quantity", "qty", "netQty", "netQuantity", "positionQty"])
    side = str(raw.get("side") or raw.get("transactionType") or "").upper()
    if not side:
        side = "BUY" if quantity >= 0 else "SELL"
    symbol = str(raw.get("symbol") or raw.get("tradingSymbol") or raw.get("securityId") or "").upper()
    price = _first_number(raw, ["price", "averagePrice", "avgPrice", "buyAvg", "sellAvg", "costPrice"])
    return {
        "symbol": symbol,
        "side": side,
        "quantity": abs(int(quantity)),
        "price": float(price),
        "raw": raw,
    }


def _first_number(raw: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = raw.get(key)
        if value in {None, ""}:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _position_key(symbol: str, side: str) -> str:
    return f"{symbol.upper()}:{side.upper()}"


def _normal_status(status: str | None) -> str:
    value = str(status or "").strip().lower().replace(" ", "_")
    if value in {"traded", "complete", "completed"}:
        return "filled"
    return value or "unknown"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_status(summary: dict[str, Any]) -> None:
    payload = {"last_run_at": datetime.now(timezone.utc).isoformat(), **summary}
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        summary.setdefault("errors", []).append(f"reconciliation status not persisted: {exc}")
