"""Idempotent append-only persistence for signal evaluation audit events.

This module never submits broker orders and is not an execution idempotency gate.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from Backend.domain.signal_event_models import SignalEvaluationEvent


_REQUIRED = ("evaluation_id", "event_type", "signal_id", "strategy", "symbol",
             "side", "signal_time", "snapshot_time", "status", "reason", "mtf_bias")


def record_signal_evaluation_event(session: Session, event: dict[str, Any]) -> tuple[int, bool]:
    """Return (row id, inserted). Caller owns transaction commit and rollback."""
    missing = [field for field in _REQUIRED if not str(event.get(field) or "").strip()]
    if missing:
        raise ValueError("Missing required signal event fields: " + ", ".join(missing))
    evidence = event.get("evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("Signal event evidence must be a dictionary")
    values = {field: str(event[field]) for field in _REQUIRED}
    values["evidence_json"] = json.dumps(evidence, sort_keys=True, default=str)
    values["evaluated_at"] = event.get("evaluated_at") or datetime.now(timezone.utc)
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        stmt = pg_insert(SignalEvaluationEvent).values(**values)
    elif dialect == "sqlite":
        stmt = sqlite_insert(SignalEvaluationEvent).values(**values)
    else:
        raise RuntimeError("Signal event idempotency requires SQLite or PostgreSQL")
    stmt = stmt.on_conflict_do_nothing(index_elements=["evaluation_id", "event_type"]).returning(SignalEvaluationEvent.id)
    inserted_id = session.execute(stmt).scalar_one_or_none()
    if inserted_id is not None:
        return int(inserted_id), True
    row_id = session.execute(
        select(SignalEvaluationEvent.id).where(
            SignalEvaluationEvent.evaluation_id == values["evaluation_id"],
            SignalEvaluationEvent.event_type == values["event_type"],
        )
    ).scalar_one()
    return int(row_id), False
