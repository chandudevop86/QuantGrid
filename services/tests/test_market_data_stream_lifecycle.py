from __future__ import annotations

import asyncio


def test_market_data_stream_shutdown_cancels_and_clears_task():
    from Backend.application import market_data_stream

    async def scenario():
        task = asyncio.create_task(asyncio.Event().wait())
        market_data_stream._task = task

        await market_data_stream.stop_market_data_stream()

        assert task.cancelled()
        assert market_data_stream._task is None

    asyncio.run(scenario())


def test_market_feed_failure_payload_does_not_expose_exception_details():
    from Backend.application.market_data_stream import _feed_down_payload

    payload = _feed_down_payload("nifty")

    assert payload == {
        "type": "market_feed_status",
        "payload": {
            "symbol": "NIFTY",
            "feed_status": "FEED DOWN",
            "error": "market_data_provider_unavailable",
        },
    }


def test_market_tick_uses_resilient_redis_publisher_and_websocket(monkeypatch):
    from Backend.application import market_data_stream

    published = []
    broadcast = []

    async def publish(channel, payload):
        published.append((channel, payload))
        return True

    async def send(message):
        broadcast.append(message)

    monkeypatch.setattr(market_data_stream.redis_service, "publish_json", publish)
    monkeypatch.setattr(market_data_stream.manager, "broadcast", send)
    tick = {"symbol": "NIFTY", "ltp": 25000}

    asyncio.run(market_data_stream.publish_tick(tick))

    assert published == [("quantgrid:market:ticks", tick)]
    assert broadcast == [{"type": "market_tick", "payload": tick}]


def test_market_stream_reuses_one_provider_service_per_lifecycle(monkeypatch):
    from Backend.application import market_data_stream

    factory_calls = []
    fetched = []

    class FakeService:
        def get_ltp(self, symbol, *, mode):
            fetched.append((symbol, mode))
            return {"symbol": symbol, "ltp": 100}

    def build_service():
        factory_calls.append(True)
        return FakeService()

    async def publish(_tick):
        return None

    async def stop_after_cycle(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(market_data_stream, "get_market_data_service", build_service)
    monkeypatch.setattr(market_data_stream, "publish_tick", publish)
    monkeypatch.setattr(market_data_stream.asyncio, "sleep", stop_after_cycle)

    async def scenario():
        try:
            await market_data_stream._market_data_loop(["NIFTY", "BANKNIFTY"])
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert len(factory_calls) == 1
    assert fetched == [("NIFTY", "paper"), ("BANKNIFTY", "paper")]


def test_invalid_market_stream_poll_interval_uses_safe_default(monkeypatch):
    from Backend.application import market_data_stream

    monkeypatch.setenv("QUANTGRID_MARKET_STREAM_POLL_SECONDS", "invalid")

    assert market_data_stream._poll_interval_seconds() == 3


def test_market_stream_retries_provider_initialization(monkeypatch):
    from Backend.application import market_data_stream

    factory_calls = []
    fetched = []
    broadcasts = []
    sleep_calls = []

    class FakeService:
        def get_ltp(self, symbol, *, mode):
            fetched.append((symbol, mode))
            return {"symbol": symbol, "ltp": 100}

    def build_service():
        factory_calls.append(True)
        if len(factory_calls) == 1:
            raise RuntimeError("temporary provider setup failure")
        return FakeService()

    async def broadcast(message):
        broadcasts.append(message)

    async def publish(_tick):
        return None

    async def sleep(_interval):
        sleep_calls.append(True)
        if len(sleep_calls) > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(market_data_stream, "get_market_data_service", build_service)
    monkeypatch.setattr(market_data_stream, "publish_tick", publish)
    monkeypatch.setattr(market_data_stream.manager, "broadcast", broadcast)
    monkeypatch.setattr(market_data_stream.asyncio, "sleep", sleep)

    async def scenario():
        try:
            await market_data_stream._market_data_loop(["NIFTY"])
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert len(factory_calls) == 2
    assert fetched == [("NIFTY", "paper")]
    assert broadcasts == [market_data_stream._feed_down_payload("NIFTY")]
