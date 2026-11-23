import json

from Backend.application import worker_progress


def test_worker_progress_tracks_scan_completion_atomically(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    monkeypatch.setenv("QUANTGRID_WORKER_PROGRESS_FILE", str(path))
    monkeypatch.setenv("QUANTGRID_AUTO_PAPER_ENABLED", " true ")
    monkeypatch.setattr(worker_progress, "_state", {})
    worker_progress.record_worker_progress("started")
    worker_progress.record_worker_progress("scan", scan_status="started")
    started = json.loads(path.read_text())
    assert started["auto_paper_enabled"] is True
    assert "last_scan_started_at" in started
    assert "last_scan_completed_at" not in started
    worker_progress.record_worker_progress("strategy")
    worker_progress.record_worker_progress("scan", scan_status="completed")
    completed = json.loads(path.read_text())
    assert completed["started_at"] == started["started_at"]
    assert completed["last_scan_status"] == "completed"
    assert completed["last_scan_completed_at"] >= completed["last_scan_started_at"]
    assert list(tmp_path.iterdir()) == [path]
