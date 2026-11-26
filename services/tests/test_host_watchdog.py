"""Watchdog does not perform remediation or broker activity."""
import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/host_watchdog.py"


def _load():
    spec = importlib.util.spec_from_file_location("host_watchdog", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_service_status_reports_inactive(monkeypatch):
    m = _load()
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: Mock(returncode=3, stdout="inactive\n"))
    assert m.service_status("quantgrid-worker") == {"name": "quantgrid-worker", "ok": False}


def test_service_status_reports_active(monkeypatch):
    m = _load()
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: Mock(returncode=0, stdout="active\n"))
    assert m.service_status("quantgrid-backend")["ok"] is True


def test_watchdog_is_read_only():
    source = PATH.read_text()
    assert "systemctl\", \"restart" not in source
    assert "submit_order" not in source
    assert "broker.place" not in source
    assert "quantgrid-backend" in source
    assert "quantgrid-worker" in source


def test_api_status_requires_healthy_application_response(monkeypatch):
    module = _load()
    for payload, expected in [
        ({"status": "ok", "services": {"db": {"healthy": True}}}, True),
        ({"status": "degraded", "services": {"db": {"healthy": False}}}, False),
        ({"status": "ok", "services": {"db": {"healthy": False}}}, False),
        ({"status": "ok", "services": {}}, False),
        ({"unexpected": "response"}, False),
        ([], False),
    ]:
        response = io.BytesIO(json.dumps(payload).encode())
        response.status = 200
        monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: response)
        assert module.api_status() == {"name": "backend_api", "ok": expected}


def test_api_status_rejects_invalid_json(monkeypatch):
    module = _load()
    response = io.BytesIO(b"<html>frontend</html>")
    response.status = 200
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: response)
    assert module.api_status() == {"name": "backend_api", "ok": False}


def test_loopback_probe_supplies_https_proxy_header(monkeypatch):
    module = _load()
    response = io.BytesIO(json.dumps({
        "status": "ok", "services": {"db": {"healthy": True}},
    }).encode())
    response.status = 200

    def local_backend(request, **kwargs):
        assert request.full_url == "http://127.0.0.1:8000/health"
        assert request.get_header("X-forwarded-proto") == "https"
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", local_backend)
    assert module.api_status()["ok"] is True


def test_option_recovery_failure_remains_visible_outside_market_hours(monkeypatch, tmp_path):
    module = _load()
    path = tmp_path / "progress.json"
    monkeypatch.setenv("QUANTGRID_WORKER_PROGRESS_FILE", str(path))
    path.write_text(json.dumps({"option_recovery_count": 2}))
    check = module.option_recovery_status()
    assert check["ok"] is False
    assert check["positions"] == 2
    path.write_text(json.dumps({"option_recovery_count": 0}))
    assert module.option_recovery_status()["ok"] is True


def test_scanner_stall_is_checked_only_during_expected_session(monkeypatch, tmp_path):
    module = _load()
    path = tmp_path / "progress.json"
    monkeypatch.setenv("QUANTGRID_WORKER_PROGRESS_FILE", str(path))
    now = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)
    path.write_text(json.dumps({
        "started_at": (now - timedelta(hours=1)).isoformat(),
        "last_progress_at": now.isoformat(), "auto_paper_enabled": True,
        "last_scan_completed_at": (now - timedelta(minutes=10)).isoformat(),
        "last_scan_status": "completed", "holidays": "",
    }))
    assert module.scanner_status(now=now)["reason"] == "scan_progress_stale"
    assert module.scanner_status(now=now.replace(hour=12))["ok"] is True
    progress = json.loads(path.read_text())
    progress["holidays"] = "2026-11-23"
    path.write_text(json.dumps(progress))
    assert module.scanner_status(now=now)["ok"] is True
    progress.update(holidays="", last_scan_completed_at=now.isoformat())
    path.write_text(json.dumps(progress))
    assert module.scanner_status(now=now)["ok"] is True


def test_webhook_notifies_failure_change_and_recovery_without_repetition(monkeypatch, tmp_path):
    module = _load()
    monkeypatch.setenv("QUANTGRID_WATCHDOG_WEBHOOK_URL", "https://alerts.example.test/notify")
    monkeypatch.setenv("QUANTGRID_WATCHDOG_NOTIFICATION_STATE", str(tmp_path / "state.json"))
    sent = []

    def notify(request, **kwargs):
        sent.append(json.loads(request.data))
        response = io.BytesIO(b"")
        response.status = 204
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", notify)
    failure = {"healthy": False, "checks": [{"name": "auto_paper_scanner", "ok": False,
                                              "reason": "scan_progress_stale"}]}
    assert module.notify_status(failure)["delivered"] is True
    assert module.notify_status(failure)["delivered"] is False
    recovered = {"healthy": True, "checks": [{"name": "auto_paper_scanner", "ok": True}]}
    assert module.notify_status(recovered)["delivered"] is True
    assert [row["healthy"] for row in sent] == [False, True]


def test_webhook_destination_is_optional_and_failed_delivery_retries(monkeypatch, tmp_path):
    module = _load()
    monkeypatch.delenv("QUANTGRID_WATCHDOG_WEBHOOK_URL", raising=False)
    report = {"healthy": False, "checks": []}
    assert module.notify_status(report)["configured"] is False
    monkeypatch.setenv("QUANTGRID_WATCHDOG_WEBHOOK_URL", "https://alerts.example.test/notify")
    state = tmp_path / "state.json"
    monkeypatch.setenv("QUANTGRID_WATCHDOG_NOTIFICATION_STATE", str(state))
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k:
                        (_ for _ in ()).throw(OSError("offline")))
    assert module.notify_status(report)["reason"] == "delivery_failed"
    assert not state.exists()


def test_broker_readiness_sanitizes_and_reports_expiry(monkeypatch):
    module = _load()
    for payload, expected in [
        ({"ready": True}, (True, "authenticated")),
        ({"ready": False, "reason": "token_expired"}, (False, "token_expired")),
        ({"ready": False, "reason": "private detail"}, (False, "broker_unavailable")),
        ([], (False, "broker_check_failed")),
    ]:
        response = io.BytesIO(json.dumps(payload).encode())
        response.status = 200
        def probe(request, **kwargs):
            assert request.full_url == "http://127.0.0.1:8000/health/broker-readiness"
            assert request.get_header("X-forwarded-proto") == "https"
            return response
        monkeypatch.setattr(module.urllib.request, "urlopen", probe)
        result = module.broker_status()
        assert (result["ok"], result["reason"]) == expected


def test_broker_readiness_network_failure(monkeypatch):
    module = _load()
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k:
                        (_ for _ in ()).throw(OSError("offline")))
    assert module.broker_status() == {"name": "dhan_authentication", "ok": False,
                                      "reason": "broker_check_failed"}
