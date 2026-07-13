from __future__ import annotations

import asyncio


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


def test_websocket_shutdown_cancels_and_clears_subscriber():
    from Backend.presentation.api.websocket_manager import ConnectionManager

    async def scenario():
        manager = ConnectionManager()
        task = asyncio.create_task(asyncio.Event().wait())
        manager._subscriber_task = task
        manager.loop = asyncio.get_running_loop()

        await manager.shutdown()

        assert task.cancelled()
        assert manager._subscriber_task is None
        assert manager.loop is None

    asyncio.run(scenario())


def test_websocket_local_broadcast_isolates_and_removes_slow_clients():
    from Backend.presentation.api.websocket_manager import ConnectionManager

    delivered = []

    class FastConnection:
        async def send_json(self, message):
            delivered.append(message)

    class SlowConnection:
        async def send_json(self, _message):
            await asyncio.Event().wait()

    async def scenario():
        manager = ConnectionManager()
        manager.send_timeout_seconds = 0.01
        fast = FastConnection()
        slow = SlowConnection()
        manager.active_connections = [slow, fast]

        await manager._broadcast_local({"type": "tick"})

        assert manager.active_connections == [fast]

    asyncio.run(scenario())
    assert delivered == [{"type": "tick"}]


def test_invalid_websocket_limits_use_safe_defaults(monkeypatch):
    from Backend.presentation.api.websocket_manager import ConnectionManager

    monkeypatch.setenv("QUANTGRID_MAX_WEBSOCKET_CONNECTIONS", "invalid")
    monkeypatch.setenv("QUANTGRID_WEBSOCKET_SEND_TIMEOUT_SECONDS", "invalid")

    manager = ConnectionManager()

    assert manager.max_connections == 100
    assert manager.send_timeout_seconds == 2.0


def test_websocket_broadcast_delivers_locally_and_ignores_redis_echo(monkeypatch):
    from Backend.presentation.api.websocket_manager import ConnectionManager
    from Backend.presentation.api import websocket_manager

    delivered = []
    published = []

    class Connection:
        async def send_json(self, message):
            delivered.append(message)

    async def publish(channel, message):
        published.append((channel, message))
        return True

    monkeypatch.setattr(websocket_manager.redis_service, "publish_json", publish)

    async def scenario():
        manager = ConnectionManager()
        manager.active_connections = [Connection()]
        message = {"type": "market_tick", "payload": {"symbol": "NIFTY"}}

        await manager.broadcast(message)
        await manager._handle_redis_message(published[0][1])
        await manager._handle_redis_message({**message, "_quantgrid_origin": "another-instance"})

        assert published[0][0] == manager.channel
        assert published[0][1]["_quantgrid_origin"] == manager.instance_id

    asyncio.run(scenario())

    assert delivered == [
        {"type": "market_tick", "payload": {"symbol": "NIFTY"}},
        {"type": "market_tick", "payload": {"symbol": "NIFTY"}},
    ]


def test_health_reports_redis_fallback_when_unconfigured(app_client, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("QUANTGRID_REDIS_URL", raising=False)

    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "connected"
    assert response.json()["trading_mode"] == "paper"
    assert response.json()["environment"] == "local"
    assert response.json()["market_data_provider"]["status"] in {"available", "degraded"}
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
