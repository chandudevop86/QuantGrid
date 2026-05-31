from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from Backend.application.job_events import publish_job_update
from Backend.application.job_store import claim_next_queued_job, create_job, update_job, utc_now
from Backend.application.notifications import alert_job_finished


class QueueBackend(Protocol):
    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    def dequeue_job(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        ...

    def mark_job_running(self, job_id: str, *, worker_id: str | None = None) -> dict[str, Any] | None:
        ...

    def mark_job_completed(self, job_id: str, result: Any | None = None) -> dict[str, Any] | None:
        ...

    def mark_job_failed(self, job_id: str, error: str) -> dict[str, Any] | None:
        ...


@dataclass
class DatabaseQueueBackend:
    """Durable queue backed by the configured SQLAlchemy/SQLite job store."""

    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        job = {
            "job_id": job_id or str(uuid4()),
            "job_type": job_type,
            "status": "queued",
            "created_at": now,
            "queued_at": now,
            **(metadata or {}),
        }
        queued = create_job(job, {**payload, "job_type": job_type})
        publish_job_update(queued)
        return queued

    def dequeue_job(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        claimed = claim_next_queued_job()
        if claimed is None:
            return None
        job, payload = claimed
        publish_job_update(job)
        return job, payload

    def mark_job_running(self, job_id: str, *, worker_id: str | None = None) -> dict[str, Any] | None:
        updates: dict[str, Any] = {
            "status": "running",
            "worker_started_at": utc_now(),
        }
        if worker_id:
            updates["worker_id"] = worker_id
        job = update_job(job_id, updates)
        if job:
            publish_job_update(job)
        return job

    def mark_job_completed(self, job_id: str, result: Any | None = None) -> dict[str, Any] | None:
        updates: dict[str, Any] = {
            "status": "completed",
            "completed_at": utc_now(),
        }
        if result is not None:
            updates["result"] = result
        job = update_job(job_id, updates)
        if job:
            publish_job_update(job)
            alert_job_finished(job)
        return job

    def mark_job_failed(self, job_id: str, error: str) -> dict[str, Any] | None:
        job = update_job(
            job_id,
            {
                "status": "failed",
                "completed_at": utc_now(),
                "error": error,
            },
        )
        if job:
            publish_job_update(job)
            alert_job_finished(job)
        return job


class RedisQueueBackend:
    """Placeholder for a future Redis/RabbitMQ-backed adapter."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("Redis/RabbitMQ queue adapters are intentionally optional for a later release.")


_backend: QueueBackend = DatabaseQueueBackend()


def enqueue_job(
    job_type: str,
    payload: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    return _backend.enqueue_job(job_type, payload, metadata=metadata, job_id=job_id)


def dequeue_job() -> tuple[dict[str, Any], dict[str, Any]] | None:
    return _backend.dequeue_job()


def mark_job_running(job_id: str, *, worker_id: str | None = None) -> dict[str, Any] | None:
    return _backend.mark_job_running(job_id, worker_id=worker_id)


def mark_job_completed(job_id: str, result: Any | None = None) -> dict[str, Any] | None:
    return _backend.mark_job_completed(job_id, result)


def mark_job_failed(job_id: str, error: str) -> dict[str, Any] | None:
    return _backend.mark_job_failed(job_id, error)
