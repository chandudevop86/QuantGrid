from __future__ import annotations


def test_health_reports_redis_fallback_when_unconfigured(app_client, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("QUANTGRID_REDIS_URL", raising=False)

    response = app_client.get("/health")

    assert response.status_code == 200
    redis = response.json()["services"]["redis"]
    assert redis["mode"] in {"fallback", "redis"}
    assert "healthy" in redis


def test_health_reports_websocket_broadcast_mode(app_client):
    response = app_client.get("/health")

    assert response.status_code == 200
    websocket = response.json()["services"]["websocket"]
    assert websocket["healthy"] is True
    assert websocket["broadcast_mode"] in {"fallback", "redis"}


def test_websocket_accepts_in_process_fallback_connection(app_client):
    with app_client.websocket_connect("/ws") as websocket:
        websocket.send_text("ping")
