from __future__ import annotations


def test_redis_fallback_is_available_but_degraded(monkeypatch):
    from Backend.presentation.api import dashboard_api

    monkeypatch.setattr(
        dashboard_api.redis_service,
        "status",
        lambda: {
            "healthy": False,
            "mode": "fallback",
            "message": "Redis unavailable; using in-process fallback.",
            "url_configured": True,
        },
    )

    status = dashboard_api._redis_status()

    assert status["connected"] is False
    assert status["healthy"] is False
    assert status["available"] is True
    assert status["degraded"] is True
    assert status["fallback_active"] is True
    assert status["mode"] == "fallback"


def test_redis_connected_is_available_and_not_degraded(monkeypatch):
    from Backend.presentation.api import dashboard_api

    monkeypatch.setattr(
        dashboard_api.redis_service,
        "status",
        lambda: {
            "healthy": True,
            "mode": "redis",
            "message": "Redis ping ok.",
            "url_configured": True,
        },
    )

    status = dashboard_api._redis_status()

    assert status["connected"] is True
    assert status["available"] is True
    assert status["degraded"] is False
    assert status["fallback_active"] is False
