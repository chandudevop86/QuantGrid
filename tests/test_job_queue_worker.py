from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def test_database_queue_interface_marks_lifecycle(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_queue, job_store

    events: list[str] = []
    monkeypatch.setattr(job_queue, "publish_job_update", lambda job: events.append(job["status"]))
    monkeypatch.setattr(job_queue, "alert_job_finished", lambda _job: None)

    queued = job_queue.enqueue_job(
        "notification",
        {"subject": "Test", "message": "Queued"},
        metadata={"symbol": "NIFTY"},
        job_id="job-queue-1",
    )

    assert queued["status"] == "queued"
    assert queued["job_type"] == "notification"
    assert job_store.count_jobs("queued") == 1

    claimed = job_queue.dequeue_job()
    assert claimed is not None
    running, payload = claimed
    assert running["status"] == "running"
    assert payload["job_type"] == "notification"

    completed = job_queue.mark_job_completed("job-queue-1", {"ok": True})
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"] == {"ok": True}
    assert events == ["queued", "running", "completed"]


def test_queue_can_mark_failed(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_queue

    monkeypatch.setattr(job_queue, "publish_job_update", lambda _job: None)
    monkeypatch.setattr(job_queue, "alert_job_finished", lambda _job: None)

    job_queue.enqueue_job("notification", {"message": "x"}, job_id="job-fail-1")
    failed = job_queue.mark_job_failed("job-fail-1", "boom")

    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error"] == "boom"


def test_worker_processes_live_analysis_job(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_queue, job_store, worker

    monkeypatch.setattr(job_queue, "publish_job_update", lambda _job: None)
    monkeypatch.setattr(job_queue, "alert_job_finished", lambda _job: None)
    monkeypatch.setattr(worker, "run_live_analysis", lambda payload: {"symbol": payload.symbol, "signals": []})

    job_queue.enqueue_job(
        "live-analysis",
        {"symbol": "NIFTY", "interval": "1m", "period": "1d", "strategy": "breakout"},
        job_id="live-job-1",
    )

    processed = worker.process_next_job()

    assert processed is not None
    assert processed["status"] == "completed"
    stored = job_store.get_job("live-job-1")
    assert stored is not None
    assert stored["result"]["symbol"] == "NIFTY"


def test_worker_marks_unsupported_job_failed(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_queue, job_store, worker

    monkeypatch.setattr(job_queue, "publish_job_update", lambda _job: None)
    monkeypatch.setattr(job_queue, "alert_job_finished", lambda _job: None)

    job_queue.enqueue_job("unknown-kind", {"value": 1}, job_id="bad-job-1")
    processed = worker.process_next_job()

    assert processed is not None
    assert processed["status"] == "failed"
    assert "Unsupported job type" in processed["error"]
    assert job_store.get_job("bad-job-1")["status"] == "failed"


def test_worker_processes_notification_job(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_queue, worker

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(job_queue, "publish_job_update", lambda _job: None)
    monkeypatch.setattr(job_queue, "alert_job_finished", lambda _job: None)
    monkeypatch.setattr(worker, "send_alert", lambda subject, message: sent.append((subject, message)))

    job_queue.enqueue_job(
        "notification",
        {"subject": "Worker alert", "message": "Done"},
        job_id="notification-job-1",
    )
    processed = worker.process_next_job()

    assert processed is not None
    assert processed["status"] == "completed"
    assert sent == [("Worker alert", "Done")]
