from __future__ import annotations

from types import SimpleNamespace

from Backend.presentation.api import broker_api


def _settings(provider: str | None):
    return SimpleNamespace(
        broker_provider=provider,
        broker_configured=provider == "dhan",
        live_trading_enabled=False,
        live_money_approved=False,
        broker_live_enabled=False,
        risk_configured=False,
        audit_logging_enabled=True,
    )


def test_broker_status_refreshes_stale_provider_settings(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setattr(broker_api, "get_settings", lambda: _settings(None))
    monkeypatch.setattr(broker_api, "reload_settings", lambda: _settings("dhan"))
    monkeypatch.setattr(
        broker_api,
        "cached_dhan_profile",
        lambda: {"provider": "dhan", "configured": True, "connected": True},
    )
    monkeypatch.setattr(broker_api, "broker_circuit_status", lambda: {"active": False})

    status = broker_api.broker_status()

    assert status["provider"] == "dhan"
    assert status["connected"] is True
    assert status["real_money_orders_enabled"] is False
