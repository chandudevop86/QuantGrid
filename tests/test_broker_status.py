from __future__ import annotations

import json

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
    monkeypatch.delenv("QUANTGRID_BROKER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)

    status = dhan_status.check_dhan_profile()

    assert status["provider"] == "dhan"
    assert status["configured"] is False
    assert status["connected"] is False
    assert status["paper_mode"] is True


def test_dhan_status_validates_profile_without_enabling_real_orders(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-123456789")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "1234567890")
    monkeypatch.setattr(dhan_status, "urlopen", lambda *_args, **_kwargs: _FakeResponse())

    status = dhan_status.check_dhan_profile()

    assert status["provider"] == "dhan"
    assert status["configured"] is True
    assert status["connected"] is True
    assert status["paper_mode"] is True
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
