from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from sqlalchemy import func

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_FILE = Path(os.getenv("JOB_STORE_DB_FILE", DATA_DIR / "dashboard_jobs.sqlite3"))
LEGACY_JOBS_FILE = DATA_DIR / "dashboard_jobs.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_job_store() -> None:
    if not _use_sqlite():
        _init_db_store()
        return
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                job_json TEXT NOT NULL
            )
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM dashboard_jobs").fetchone()[0]
        if count == 0:
            _migrate_legacy_jobs(connection)


def _migrate_legacy_jobs(connection: sqlite3.Connection) -> None:
    if not LEGACY_JOBS_FILE.exists():
        return

    try:
        legacy_jobs = json.loads(LEGACY_JOBS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    for job_id, job in legacy_jobs.items():
        if not isinstance(job, dict):
            continue
        if job.get("status") == "queued" and not job.get("queued_at"):
            job = {
                **job,
                "status": "stale",
                "note": "This job was queued before durable live-analysis jobs were enabled.",
            }
        created_at = str(job.get("created_at") or utc_now())
        connection.execute(
            """
            INSERT OR IGNORE INTO dashboard_jobs
                (job_id, status, created_at, updated_at, payload_json, job_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(job.get("job_id") or job_id),
                str(job.get("status") or "unknown"),
                created_at,
                str(job.get("completed_at") or job.get("worker_started_at") or created_at),
                json.dumps({}),
                json.dumps(job),
            ),
        )


def create_job(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    init_job_store()
    if not _use_sqlite():
        return _db_create_job(job, payload)
    now = utc_now()
    job = {**job, "updated_at": now}
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO dashboard_jobs
                (job_id, status, created_at, updated_at, payload_json, job_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job["job_id"],
                job["status"],
                job["created_at"],
                now,
                json.dumps(payload),
                json.dumps(job),
            ),
        )
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    init_job_store()
    if not _use_sqlite():
        return _db_get_job(job_id)
    with _connect() as connection:
        row = connection.execute(
            "SELECT job_json FROM dashboard_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return json.loads(row["job_json"]) if row else None


def get_job_payload(job_id: str) -> dict[str, Any] | None:
    init_job_store()
    if not _use_sqlite():
        return _db_get_job_payload(job_id)
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM dashboard_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def update_job(job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    init_job_store()
    if not _use_sqlite():
        return _db_update_job(job_id, updates)
    with _connect() as connection:
        row = connection.execute(
            "SELECT job_json FROM dashboard_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None

        job = json.loads(row["job_json"])
        job.update(updates)
        job["updated_at"] = utc_now()
        connection.execute(
            """
            UPDATE dashboard_jobs
            SET status = ?, updated_at = ?, job_json = ?
            WHERE job_id = ?
            """,
            (str(job.get("status") or "unknown"), job["updated_at"], json.dumps(job), job_id),
        )
    return job


def list_jobs() -> list[dict[str, Any]]:
    init_job_store()
    if not _use_sqlite():
        return _db_list_jobs()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT job_json FROM dashboard_jobs ORDER BY created_at DESC"
        ).fetchall()
    return [json.loads(row["job_json"]) for row in rows]


def count_jobs(status: str | None = None) -> int:
    init_job_store()
    if not _use_sqlite():
        return _db_count_jobs(status)
    with _connect() as connection:
        if status is None:
            return int(connection.execute("SELECT COUNT(*) FROM dashboard_jobs").fetchone()[0])
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM dashboard_jobs WHERE status = ?",
                (status,),
            ).fetchone()[0]
        )


def claim_next_queued_job() -> tuple[dict[str, Any], dict[str, Any]] | None:
    init_job_store()
    if not _use_sqlite():
        return _db_claim_next_queued_job()
    with _connect() as connection:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT job_id, payload_json, job_json
            FROM dashboard_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None

        job = json.loads(row["job_json"])
        job.update({"status": "running", "worker_started_at": utc_now(), "updated_at": utc_now()})
        connection.execute(
            """
            UPDATE dashboard_jobs
            SET status = 'running', updated_at = ?, job_json = ?
            WHERE job_id = ? AND status = 'queued'
            """,
            (job["updated_at"], json.dumps(job), row["job_id"]),
        )
        connection.execute("COMMIT")
        return job, json.loads(row["payload_json"])


def claim_job(job_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    init_job_store()
    if not _use_sqlite():
        return _db_claim_job(job_id)
    with _connect() as connection:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT payload_json, job_json
            FROM dashboard_jobs
            WHERE job_id = ? AND status = 'queued'
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None

        job = json.loads(row["job_json"])
        job.update({"status": "running", "worker_started_at": utc_now(), "updated_at": utc_now()})
        connection.execute(
            """
            UPDATE dashboard_jobs
            SET status = 'running', updated_at = ?, job_json = ?
            WHERE job_id = ? AND status = 'queued'
            """,
            (job["updated_at"], json.dumps(job), job_id),
        )
        connection.execute("COMMIT")
        return job, json.loads(row["payload_json"])


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _init_db_store() -> None:
    from Backend.core.database import Base, engine
    import Backend.domain.trading_store_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _db_create_job(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    now = utc_now()
    job = {**job, "updated_at": now}
    with SessionLocal() as db:
        db.add(JobRecord(job_id=job["job_id"], status=job["status"], created_at=job["created_at"], updated_at=now, payload_json=json.dumps(payload), job_json=json.dumps(job)))
        db.commit()
    return job


def _db_get_job(job_id: str) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        row = db.get(JobRecord, job_id)
        return json.loads(row.job_json) if row else None


def _db_get_job_payload(job_id: str) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        row = db.get(JobRecord, job_id)
        return json.loads(row.payload_json) if row else None


def _db_update_job(job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        row = db.get(JobRecord, job_id)
        if row is None:
            return None
        job = json.loads(row.job_json)
        job.update(updates)
        job["updated_at"] = utc_now()
        row.status = str(job.get("status") or "unknown")
        row.updated_at = job["updated_at"]
        row.job_json = json.dumps(job)
        db.commit()
    return job


def _db_list_jobs() -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        rows = db.query(JobRecord).order_by(JobRecord.created_at.desc()).all()
        return [json.loads(row.job_json) for row in rows]


def _db_count_jobs(status: str | None = None) -> int:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        query = db.query(func.count(JobRecord.job_id))
        if status is not None:
            query = query.filter(JobRecord.status == status)
        return int(query.scalar() or 0)


def _db_claim_next_queued_job() -> tuple[dict[str, Any], dict[str, Any]] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        row = (
            db.query(JobRecord)
            .filter(JobRecord.status == "queued")
            .order_by(JobRecord.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            return None
        job = json.loads(row.job_json)
        job.update({"status": "running", "worker_started_at": utc_now(), "updated_at": utc_now()})
        row.status = "running"
        row.updated_at = job["updated_at"]
        row.job_json = json.dumps(job)
        payload = json.loads(row.payload_json)
        db.commit()
        return job, payload


def _db_claim_job(job_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import JobRecord

    with SessionLocal() as db:
        row = db.query(JobRecord).filter(JobRecord.job_id == job_id, JobRecord.status == "queued").with_for_update().first()
        if row is None:
            return None
        job = json.loads(row.job_json)
        job.update({"status": "running", "worker_started_at": utc_now(), "updated_at": utc_now()})
        row.status = "running"
        row.updated_at = job["updated_at"]
        row.job_json = json.dumps(job)
        payload = json.loads(row.payload_json)
        db.commit()
        return job, payload
