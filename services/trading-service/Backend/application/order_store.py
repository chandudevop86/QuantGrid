from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


ORDER_STATUSES = {
    "requested",
    "risk_approved",
    "broker_submitted",
    "pending",
    "open",
    "partially_filled",
    "filled",
    "cancelled",
    "rejected",
    "failed",
}

POSITION_CREATING_STATUSES = {"broker_submitted", "pending", "open", "partially_filled", "filled"}
TERMINAL_STATUSES = {"filled", "cancelled", "rejected", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_order_store() -> None:
    from Backend.core.database import Base, engine
    import Backend.domain.trading_store_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def create_order(payload: dict[str, Any]) -> dict[str, Any]:
    init_order_store()
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import OrderRecord

    now = utc_now()
    row = {
        "local_order_id": str(payload.get("local_order_id") or f"ORD-{uuid4().hex[:16]}"),
        "broker_order_id": payload.get("broker_order_id"),
        "symbol": str(payload.get("symbol") or "").upper(),
        "side": str(payload.get("side") or "").upper(),
        "quantity": int(payload.get("quantity") or 0),
        "entry_price": _float_or_none(payload.get("entry_price") if "entry_price" in payload else payload.get("price")),
        "status": _validate_status(str(payload.get("status") or "requested")),
        "status_reason": payload.get("status_reason"),
        "created_at": str(payload.get("created_at") or now),
        "updated_at": str(payload.get("updated_at") or now),
    }
    with SessionLocal() as db:
        record = OrderRecord(**row)
        db.add(record)
        db.commit()
        db.refresh(record)
        return _record_to_dict(record)


def get_order(local_order_id: str) -> dict[str, Any] | None:
    init_order_store()
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import OrderRecord

    with SessionLocal() as db:
        row = db.query(OrderRecord).filter(OrderRecord.local_order_id == local_order_id).first()
        return _record_to_dict(row) if row else None


def list_orders(limit: int = 100) -> list[dict[str, Any]]:
    init_order_store()
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import OrderRecord

    with SessionLocal() as db:
        rows = (
            db.query(OrderRecord)
            .order_by(OrderRecord.updated_at.desc(), OrderRecord.created_at.desc())
            .limit(max(1, min(int(limit), 500)))
            .all()
        )
        return [_record_to_dict(row) for row in rows]


def transition_order(
    local_order_id: str,
    status: str,
    *,
    status_reason: str | None = None,
    broker_order_id: str | None = None,
    entry_price: float | None = None,
) -> tuple[dict[str, Any], str]:
    init_order_store()
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import OrderRecord

    next_status = _validate_status(status)
    with SessionLocal() as db:
        row = db.query(OrderRecord).filter(OrderRecord.local_order_id == local_order_id).first()
        if row is None:
            raise ValueError("order not found")
        previous = row.status
        row.status = next_status
        if status_reason is not None:
            row.status_reason = status_reason
        if broker_order_id is not None:
            row.broker_order_id = broker_order_id
        if entry_price is not None:
            row.entry_price = float(entry_price)
        row.updated_at = utc_now()
        db.commit()
        db.refresh(row)
        return _record_to_dict(row), previous


def broker_status_to_order_status(status: str | None, *, confirmed: bool = False) -> str:
    value = str(status or "").strip().lower().replace(" ", "_")
    if value in {"confirmed", "submitted"}:
        return "broker_submitted" if confirmed else "pending"
    if value in {"pending", "transit", "trigger_pending", "validation_pending"}:
        return "pending"
    if value in {"open", "after_market_order_req_received"}:
        return "open"
    if value in {"partially_filled", "partial", "part_filled"}:
        return "partially_filled"
    if value in {"filled", "traded", "complete", "completed"}:
        return "filled"
    if value in {"cancelled", "canceled"}:
        return "cancelled"
    if value in {"rejected", "not_found"}:
        return "rejected"
    if value in {"failed", "expired"}:
        return "failed"
    return "broker_submitted" if confirmed else "pending"


def should_create_position(status: str) -> bool:
    return status in POSITION_CREATING_STATUSES


def _record_to_dict(record: Any) -> dict[str, Any]:
    return {
        "local_order_id": record.local_order_id,
        "broker_order_id": record.broker_order_id,
        "symbol": record.symbol,
        "side": record.side,
        "quantity": record.quantity,
        "entry_price": record.entry_price,
        "status": record.status,
        "status_reason": record.status_reason,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in ORDER_STATUSES:
        raise ValueError(f"unsupported order status: {status}")
    return normalized


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)
