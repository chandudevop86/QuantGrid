from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_FILE: Path | str = Path(os.getenv("BACKTEST_JOB_STORE_DB_FILE", DATA_DIR / "backtest_jobs.sqlite3"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_backtest_job_store() -> None:
    if not _use_sqlite():
        _init_db_store()
        return
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                job_json TEXT NOT NULL
            )
            """
        )


def create_backtest_job(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    init_backtest_job_store()
    now = utc_now()
    job = {**job, "updated_at": now}
    if not _use_sqlite():
        return _db_create_backtest_job(job, payload)
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO backtest_jobs
                (job_id, status, created_at, updated_at, payload_json, job_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job["job_id"],
                job["status"],
                job["created_at"],
                job["updated_at"],
                json.dumps(payload),
                json.dumps(job),
            ),
        )
    return job


def get_backtest_job_record(job_id: str) -> dict[str, Any] | None:
    init_backtest_job_store()
    if not _use_sqlite():
        return _db_get_backtest_job_record(job_id)
    with _connect() as connection:
        row = connection.execute("SELECT job_json FROM backtest_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return json.loads(row["job_json"]) if row else None


def update_backtest_job_record(job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    init_backtest_job_store()
    if not _use_sqlite():
        return _db_update_backtest_job_record(job_id, updates)
    with _connect() as connection:
        row = connection.execute("SELECT job_json FROM backtest_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = json.loads(row["job_json"])
        job.update(updates)
        job["updated_at"] = utc_now()
        connection.execute(
            """
            UPDATE backtest_jobs
            SET status = ?, updated_at = ?, job_json = ?
            WHERE job_id = ?
            """,
            (str(job.get("status") or "UNKNOWN"), job["updated_at"], json.dumps(job), job_id),
        )
    return job


def list_backtest_job_records(limit: int = 20) -> list[dict[str, Any]]:
    init_backtest_job_store()
    limit = max(1, min(int(limit), 100))
    if not _use_sqlite():
        return _db_list_backtest_job_records(limit)
    with _connect() as connection:
        rows = connection.execute(
            "SELECT job_json FROM backtest_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["job_json"]) for row in rows]


def claim_recoverable_backtest_jobs(owner: str, *, limit: int = 100, lease_seconds: int = 300) -> list[dict[str, Any]]:
    init_backtest_job_store()
    limit = max(1, min(int(limit), 100))
    if not _use_sqlite():
        return _db_claim_recoverable_backtest_jobs(owner, limit=limit, lease_seconds=lease_seconds)

    claimed: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
    with _connect() as connection:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT job_id, job_json
            FROM backtest_jobs
            WHERE status IN ('QUEUED', 'RUNNING', 'TIMEOUT')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            job = json.loads(row["job_json"])
            if not _lease_available(job, now):
                continue
            job["recovery_owner"] = owner
            job["recovery_lease_until"] = lease_until
            job["updated_at"] = utc_now()
            connection.execute(
                """
                UPDATE backtest_jobs
                SET updated_at = ?, job_json = ?
                WHERE job_id = ?
                """,
                (job["updated_at"], json.dumps(job), row["job_id"]),
            )
            claimed.append(job)
        connection.execute("COMMIT")
    return claimed


def clear_backtest_jobs_for_tests() -> None:
    init_backtest_job_store()
    if not _use_sqlite():
        _db_clear_backtest_jobs_for_tests()
        return
    with _connect() as connection:
        connection.execute("DELETE FROM backtest_jobs")


def _lease_available(job: dict[str, Any], now: datetime) -> bool:
    if job.get("cancel_requested"):
        return False
    lease_until = _parse_time(job.get("recovery_lease_until"))
    return lease_until is None or lease_until <= now


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _connect() -> sqlite3.Connection:
    db_file = Path(DB_FILE)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_file, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _init_db_store() -> None:
    from Backend.core.database import init_database

    init_database()


def _db_create_backtest_job(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import BacktestJobRecord

    with SessionLocal() as db:
        db.add(
            BacktestJobRecord(
                job_id=job["job_id"],
                status=job["status"],
                created_at=job["created_at"],
                updated_at=job["updated_at"],
                payload_json=json.dumps(payload),
                job_json=json.dumps(job),
            )
        )
        db.commit()
    return job


def _db_get_backtest_job_record(job_id: str) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import BacktestJobRecord

    with SessionLocal() as db:
        row = db.get(BacktestJobRecord, job_id)
        return json.loads(row.job_json) if row else None


def _db_update_backtest_job_record(job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import BacktestJobRecord

    with SessionLocal() as db:
        row = db.get(BacktestJobRecord, job_id)
        if row is None:
            return None
        job = json.loads(row.job_json)
        job.update(updates)
        job["updated_at"] = utc_now()
        row.status = str(job.get("status") or "UNKNOWN")
        row.updated_at = job["updated_at"]
        row.job_json = json.dumps(job)
        db.commit()
    return job


def _db_list_backtest_job_records(limit: int) -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import BacktestJobRecord

    with SessionLocal() as db:
        rows = db.query(BacktestJobRecord).order_by(BacktestJobRecord.created_at.desc()).limit(limit).all()
        return [json.loads(row.job_json) for row in rows]


def _db_claim_recoverable_backtest_jobs(owner: str, *, limit: int, lease_seconds: int) -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import BacktestJobRecord

    claimed: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
    with SessionLocal() as db:
        rows = (
            db.query(BacktestJobRecord)
            .filter(BacktestJobRecord.status.in_(["QUEUED", "RUNNING", "TIMEOUT"]))
            .order_by(BacktestJobRecord.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
            .all()
        )
        for row in rows:
            job = json.loads(row.job_json)
            if not _lease_available(job, now):
                continue
            job["recovery_owner"] = owner
            job["recovery_lease_until"] = lease_until
            job["updated_at"] = utc_now()
            row.updated_at = job["updated_at"]
            row.job_json = json.dumps(job)
            claimed.append(job)
        db.commit()
    return claimed


def _db_clear_backtest_jobs_for_tests() -> None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import BacktestJobRecord

    with SessionLocal() as db:
        db.query(BacktestJobRecord).delete()
        db.commit()
