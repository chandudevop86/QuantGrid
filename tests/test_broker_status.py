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


def test_dhan_profile_cache_reuses_health_and_invalidates_for_new_credentials(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-one")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    calls = 0

    def profile_check(timeout=8.0):
        nonlocal calls
        calls += 1
        return {"provider": "dhan", "connected": True, "timeout": timeout}

    monkeypatch.setattr(dhan_status, "check_dhan_profile", profile_check)

    first = dhan_status.cached_dhan_profile(timeout=1.5)
    second = dhan_status.cached_dhan_profile(timeout=1.5)
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-two")
    third = dhan_status.cached_dhan_profile(timeout=1.5)

    assert first == second
    assert third["connected"] is True
    assert calls == 2


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


def test_broker_status_uses_shared_profile_cache(monkeypatch):
    from Backend.presentation.api import broker_api

    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setattr(
        broker_api,
        "cached_dhan_profile",
        lambda: {"provider": "dhan", "configured": True, "connected": True},
    )
    monkeypatch.setattr(
        broker_api,
        "check_dhan_profile",
        lambda: (_ for _ in ()).throw(AssertionError("status route bypassed shared cache")),
    )

    assert broker_api.broker_status()["connected"] is True


def test_dhan_option_chain_status_reports_data_api_failure(monkeypatch):
    from Backend.presentation.api import broker_api, market_api

    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setattr(broker_api, "check_dhan_profile", lambda: {"connected": True, "error": None})
    monkeypatch.setattr(market_api, "_dhan_underlying", lambda symbol: (13, "IDX_I"))
    monkeypatch.setattr(
        market_api,
        "_dhan_option_provider_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Dhan option-chain API rejected the request without an error message.")),
    )

    status = broker_api._dhan_option_chain_readiness("NIFTY")

    assert status["profile_connected"] is True
    assert status["option_chain_access"] is False
    assert status["data_api_connected"] is False
    assert "Data APIs" in status["suggested_actions"][0]
    assert "without an error message" in status["message"]


def test_dhan_option_chain_status_reports_expiry_success(monkeypatch):
    from Backend.presentation.api import broker_api, market_api

    monkeypatch.setattr(broker_api, "check_dhan_profile", lambda: {"connected": True, "error": None})
    monkeypatch.setattr(market_api, "_dhan_underlying", lambda symbol: (13, "IDX_I"))
    monkeypatch.setattr(
        market_api,
        "_dhan_option_provider_payload",
        lambda path, body: {"status": "success", "data": {"data": ["2026-07-30"]}},
    )

    status = broker_api._dhan_option_chain_readiness("NIFTY")

    assert status["profile_connected"] is True
    assert status["option_chain_access"] is True
    assert status["data_api_connected"] is True
    assert status["expiry_available"] is True
    assert status["expiry"] == "2026-07-30"

def test_trader_cannot_persist_global_dhan_credentials(app_client, monkeypatch):
    from Backend.presentation.api import broker_api
    from conftest import admin_headers

    monkeypatch.setattr(broker_api, "check_dhan_profile", lambda: {"provider": "dhan", "connected": True, "error": None})

    create = app_client.post(
        "/admin/users/create",
        json={"username": "trader-persist", "password": "TraderPass1!", "role": "trader"},
        headers=admin_headers(app_client),
    )
    assert create.status_code == 200
    login = app_client.post("/auth/login", json={"username": "trader-persist", "password": "TraderPass1!"})
    assert login.status_code == 200
    trader_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = app_client.post(
        "/broker/dhan/login",
        json={"client_id": "1234567890", "access_token": "token-123456789", "persist": True},
        headers=trader_headers,
    )
    assert denied.status_code == 403

    allowed = app_client.post(
        "/broker/dhan/login",
        json={"client_id": "1234567890", "access_token": "token-123456789", "persist": False},
        headers=trader_headers,
    )
    assert allowed.status_code == 200

