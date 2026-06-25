from __future__ import annotations

import json
import base64
from io import BytesIO
from urllib.error import HTTPError

from Backend.infrastructure.broker import dhan_status
from Backend.presentation.api.broker_api import broker_status


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps({"dhanClientId": "1234567890", "clientName": "Paper User"}).encode("utf-8")


def test_dhan_status_is_paper_mode_without_token(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.delenv("QUANTGRID_BROKER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)

    status = dhan_status.check_dhan_profile()

    assert status["provider"] == "dhan"
    assert status["configured"] is False
    assert status["connected"] is False
    assert status["paper_mode"] is True
    assert status["paper_only"] is True
    assert status["error"] == "token_missing"


def test_dhan_status_reports_missing_client_id(monkeypatch):
    monkeypatch.delenv("QUANTGRID_BROKER_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")

    status = dhan_status.check_dhan_profile()

    assert status["connected"] is False
    assert status["authenticated"] is False
    assert status["error"] == "missing_client_id"


def test_dhan_status_reports_expired_token(monkeypatch):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": 1}).encode()).rstrip(b"=").decode()
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", f"{header}.{payload}.sig")

    status = dhan_status.check_dhan_profile()

    assert status["connected"] is False
    assert status["error"] == "token_expired"


def test_dhan_status_reports_invalid_token(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")

    def fake_urlopen(*_args, **_kwargs):
        raise HTTPError("https://api.dhan.co/v2/profile", 401, "unauthorized", {}, BytesIO(b"{}"))

    monkeypatch.setattr(dhan_status, "urlopen", fake_urlopen)

    status = dhan_status.check_dhan_profile()

    assert status["connected"] is False
    assert status["authenticated"] is False
    assert status["error"] == "invalid_token"


def test_dhan_status_validates_profile_without_enabling_real_orders(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setattr(dhan_status, "urlopen", lambda *_args, **_kwargs: _FakeResponse())

    status = dhan_status.check_dhan_profile()

    assert status["provider"] == "dhan"
    assert status["configured"] is True
    assert status["connected"] is True
    assert status["authenticated"] is True
    assert status["paper_mode"] is True
    assert status["paper_only"] is True
    assert status["account_name"] == "Paper User"


def test_broker_status_keeps_real_money_orders_disabled(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setenv("QUANTGRID_ENABLE_LIVE_TRADING", "false")
    monkeypatch.setattr(dhan_status, "urlopen", lambda *_args, **_kwargs: _FakeResponse())

    status = broker_status()

    assert status["provider"] == "dhan"
    assert status["connected"] is True
    assert status["paper_mode"] is True
    assert status["live_trading_enabled"] is False
    assert status["real_money_orders_enabled"] is False
