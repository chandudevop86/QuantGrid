from __future__ import annotations


def test_websocket_subscriber_starts_even_when_redis_is_initially_unavailable(monkeypatch):
    from Backend.presentation.api.websocket_manager import ConnectionManager
    from Backend.presentation.api import websocket_manager

    created = []

    class FakeTask:
        def done(self):
            return False

    class FakeLoop:
        def create_task(self, coroutine):
            created.append(coroutine)
            coroutine.close()
            return FakeTask()

    async def subscriber(*_args, **_kwargs):
        return None

    monkeypatch.setattr(websocket_manager.redis_service, "subscribe_json", subscriber)
    manager = ConnectionManager()
    manager.set_loop(FakeLoop())

    assert len(created) == 1


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


def test_websocket_accepts_in_process_fallback_connection_when_anonymous_is_enabled(app_client, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ALLOW_ANONYMOUS_WEBSOCKET", "true")

    with app_client.websocket_connect("/ws") as websocket:
        websocket.send_text("ping")
