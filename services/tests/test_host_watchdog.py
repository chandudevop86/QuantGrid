"""Watchdog does not perform remediation or broker activity."""
import importlib.util
import io
import json
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
