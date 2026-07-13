from __future__ import annotations

import json

from Backend.application.redis_service import RedisService


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttl_values: dict[str, int] = {}

    def set(self, key: str, value: str, ex: int, nx: bool = False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttl_values[key] = ex
        return True

    def get(self, key: str):
        value = self.values.get(key)
        return value.encode("utf-8") if value is not None else None

    def ttl(self, key: str):
        return self.ttl_values.get(key, -2)

    def eval(self, _script: str, _key_count: int, key: str, token: str):
        if self.values.get(key) != token:
            return 0
        del self.values[key]
        self.ttl_values.pop(key, None)
        return 1


def test_worker_heartbeat_round_trip_uses_expiring_redis_key():
    service = RedisService()
    fake = FakeRedis()
    service.client = fake
    payload = {"worker_id": "worker-1", "status": "RUNNING", "last_seen": "2026-07-12T10:00:00+00:00"}

    assert service.write_worker_heartbeat(payload, ttl_seconds=15) is True
    assert json.loads(fake.values[service.WORKER_HEARTBEAT_KEY]) == payload
    assert fake.ttl_values[service.WORKER_HEARTBEAT_KEY] == 15
    assert service.read_worker_heartbeat() == payload


def test_worker_heartbeat_is_unavailable_without_redis():
    service = RedisService()

    assert service.write_worker_heartbeat({"status": "RUNNING"}) is False
    assert service.read_worker_heartbeat() is None


def test_provider_cooldown_round_trip_uses_shared_expiring_key():
    service = RedisService()
    fake = FakeRedis()
    service.client = fake

    assert service.start_cooldown("dhan-option-chain", ttl_seconds=300) is True
    assert service.cooldown_remaining("dhan-option-chain") == 300
    assert fake.values[f"{service.COOLDOWN_KEY_PREFIX}dhan-option-chain"] == "1"


def test_provider_cooldown_falls_back_when_redis_is_unavailable():
    service = RedisService()

    assert service.start_cooldown("dhan-option-chain", ttl_seconds=300) is False
    assert service.cooldown_remaining("dhan-option-chain") is None


def test_distributed_lock_requires_owner_token_and_expires():
    service = RedisService()
    fake = FakeRedis()
    service.client = fake

    owner = service.acquire_lock("dhan-option-chain-fetch", ttl_seconds=20)

    assert owner
    assert service.acquire_lock("dhan-option-chain-fetch", ttl_seconds=20) == ""
    assert service.release_lock("dhan-option-chain-fetch", "not-the-owner") is False
    assert service.release_lock("dhan-option-chain-fetch", owner) is True
    assert service.acquire_lock("dhan-option-chain-fetch", ttl_seconds=20)
