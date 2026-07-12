from __future__ import annotations

import json

from Backend.application.redis_service import RedisService


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def set(self, key: str, value: str, ex: int):
        self.values[key] = value
        self.ttl[key] = ex

    def get(self, key: str):
        value = self.values.get(key)
        return value.encode("utf-8") if value is not None else None


def test_worker_heartbeat_round_trip_uses_expiring_redis_key():
    service = RedisService()
    fake = FakeRedis()
    service.client = fake
    payload = {"worker_id": "worker-1", "status": "RUNNING", "last_seen": "2026-07-12T10:00:00+00:00"}

    assert service.write_worker_heartbeat(payload, ttl_seconds=15) is True
    assert json.loads(fake.values[service.WORKER_HEARTBEAT_KEY]) == payload
    assert fake.ttl[service.WORKER_HEARTBEAT_KEY] == 15
    assert service.read_worker_heartbeat() == payload


def test_worker_heartbeat_is_unavailable_without_redis():
    service = RedisService()

    assert service.write_worker_heartbeat({"status": "RUNNING"}) is False
    assert service.read_worker_heartbeat() is None
