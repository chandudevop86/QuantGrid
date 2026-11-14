"""Watchdog does not perform remediation or broker activity."""
import importlib.util
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest

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


@pytest.mark.parametrize(
    ("body", "expected"),
    [(b'{"status":"ok"}', True), (b'{"status":"degraded"}', False), (b'<html>', False)],
)
def test_api_status_checks_health_body(monkeypatch, body, expected):
    module = _load()
    response = BytesIO(body)
    response.status = 200
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: response)
    assert module.api_status() == {"name": "backend_api", "ok": expected}
