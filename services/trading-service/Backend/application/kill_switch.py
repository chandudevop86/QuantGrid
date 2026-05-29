from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from Backend.application.paper_trade_store import DATA_DIR, utc_now


DB_FILE = Path(DATA_DIR) / "risk_state.sqlite3"


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_kill_switch_store() -> None:
    if not _use_sqlite():
        _db_init_kill_switch_store()
        return
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS kill_switch (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                active INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                activated_by TEXT,
                deactivated_by TEXT,
                activated_at TEXT,
                deactivated_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO kill_switch (id, active, updated_at)
            VALUES (1, 0, ?)
            """,
            (utc_now(),),
        )


def kill_switch_status() -> dict[str, Any]:
    init_kill_switch_store()
    if not _use_sqlite():
        return _db_kill_switch_status()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM kill_switch WHERE id = 1").fetchone()
    return _present(row)


def activate_kill_switch(*, reason: str | None, actor: str | None) -> dict[str, Any]:
    init_kill_switch_store()
    if not _use_sqlite():
        return _db_activate_kill_switch(reason=reason, actor=actor)
    now = utc_now()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE kill_switch
            SET active = 1,
                reason = ?,
                activated_by = ?,
                activated_at = COALESCE(activated_at, ?),
                deactivated_by = NULL,
                deactivated_at = NULL,
                updated_at = ?
            WHERE id = 1
            """,
            (reason or "Manual kill switch activation", actor, now, now),
        )
    return kill_switch_status()


def deactivate_kill_switch(*, actor: str | None) -> dict[str, Any]:
    init_kill_switch_store()
    if not _use_sqlite():
        return _db_deactivate_kill_switch(actor=actor)
    now = utc_now()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE kill_switch
            SET active = 0,
                deactivated_by = ?,
                deactivated_at = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (actor, now, now),
        )
    return kill_switch_status()


def _present(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {
            "active": False,
            "reason": None,
            "activated_by": None,
            "deactivated_by": None,
            "activated_at": None,
            "deactivated_at": None,
            "updated_at": None,
        }
    return {
        "active": bool(row["active"]),
        "reason": row["reason"],
        "activated_by": row["activated_by"],
        "deactivated_by": row["deactivated_by"],
        "activated_at": row["activated_at"],
        "deactivated_at": row["deactivated_at"],
        "updated_at": row["updated_at"],
    }


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _db_init_kill_switch_store() -> None:
    from Backend.core.database import Base, SessionLocal, engine
    from Backend.domain.trading_store_models import RiskStateRecord
    import Backend.domain.trading_store_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        row = db.get(RiskStateRecord, 1)
        if row is None:
            db.add(RiskStateRecord(id=1, active=0, updated_at=utc_now()))
            db.commit()


def _db_kill_switch_status() -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import RiskStateRecord

    with SessionLocal() as db:
        row = db.get(RiskStateRecord, 1)
        return _present_record(row)


def _db_activate_kill_switch(*, reason: str | None, actor: str | None) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import RiskStateRecord

    now = utc_now()
    with SessionLocal() as db:
        row = db.get(RiskStateRecord, 1)
        if row is None:
            row = RiskStateRecord(id=1, active=0, updated_at=now)
            db.add(row)
            db.flush()
        row.active = 1
        row.reason = reason or "Manual kill switch activation"
        row.activated_by = actor
        row.activated_at = row.activated_at or now
        row.deactivated_by = None
        row.deactivated_at = None
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return _present_record(row)


def _db_deactivate_kill_switch(*, actor: str | None) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import RiskStateRecord

    now = utc_now()
    with SessionLocal() as db:
        row = db.get(RiskStateRecord, 1)
        if row is None:
            row = RiskStateRecord(id=1, active=0, updated_at=now)
            db.add(row)
            db.flush()
        row.active = 0
        row.deactivated_by = actor
        row.deactivated_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return _present_record(row)


def _present_record(row: Any | None) -> dict[str, Any]:
    if row is None:
        return {
            "active": False,
            "reason": None,
            "activated_by": None,
            "deactivated_by": None,
            "activated_at": None,
            "deactivated_at": None,
            "updated_at": None,
        }
    return {
        "active": bool(row.active),
        "reason": row.reason,
        "activated_by": row.activated_by,
        "deactivated_by": row.deactivated_by,
        "activated_at": row.activated_at,
        "deactivated_at": row.deactivated_at,
        "updated_at": row.updated_at,
    }
