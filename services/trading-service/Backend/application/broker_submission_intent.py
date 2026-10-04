"""Durable fail-closed broker submission claim primitives.

Call claim_submission before broker I/O, then mark_submission_started before
sending. A duplicate or ambiguous claim must never trigger a broker resend.
This module does not itself enable live execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from Backend.core.database import SessionLocal


def claim_submission(local_order_id: str, logical_key: str) -> dict:
    if not local_order_id or not logical_key:
        raise ValueError("local_order_id and logical_key are required")
    correlation_id = f"QG-{uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        with SessionLocal.begin() as db:
            db.execute(text(
                "INSERT INTO broker_submission_intents "
                "(local_order_id, logical_key, correlation_id, status, created_at, updated_at) "
                "VALUES (:id, :key, :correlation, 'claimed', :now, :now)"
            ), {"id": local_order_id, "key": logical_key.strip().upper(),
                "correlation": correlation_id, "now": now})
    except IntegrityError as exc:
        raise ValueError("DUPLICATE_OR_UNRESOLVED_BROKER_INTENT") from exc
    return {"local_order_id": local_order_id, "logical_key": logical_key.strip().upper(),
            "correlation_id": correlation_id, "status": "claimed"}


def mark_submission_started(local_order_id: str) -> None:
    """Commit the ambiguous boundary BEFORE broker network I/O."""
    with SessionLocal.begin() as db:
        result = db.execute(text(
            "UPDATE broker_submission_intents SET status = 'reconciliation_required', "
            "updated_at = :now WHERE local_order_id = :id AND status = 'claimed'"
        ), {"id": local_order_id, "now": datetime.now(timezone.utc).isoformat()})
        if result.rowcount != 1:
            raise ValueError("BROKER_INTENT_NOT_CLAIMED")


def record_broker_evidence(local_order_id: str, broker_order_id: str, status: str) -> None:
    """Only call after authoritative broker confirmation; never on a missing lookup."""
    if not broker_order_id or status not in {
        "submitted", "open", "partially_filled", "filled", "cancelled", "rejected"
    }:
        raise ValueError("AUTHORITATIVE_BROKER_EVIDENCE_REQUIRED")
    with SessionLocal.begin() as db:
        result = db.execute(text(
            "UPDATE broker_submission_intents SET broker_order_id = :broker, "
            "status = :status, updated_at = :now "
            "WHERE local_order_id = :id AND (status = 'reconciliation_required' "
            "OR (broker_order_id = :broker AND status IN "
            "('submitted', 'open', 'partially_filled')))"
        ), {"broker": broker_order_id, "status": status,
            "now": datetime.now(timezone.utc).isoformat(), "id": local_order_id})
        if result.rowcount != 1:
            raise ValueError("BROKER_INTENT_NOT_AWAITING_RECONCILIATION")
