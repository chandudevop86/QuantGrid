"""Regression coverage for request-time schema initialization contention."""

from concurrent.futures import ThreadPoolExecutor
import time

from Backend.core import database


def test_init_database_runs_once_for_concurrent_callers(monkeypatch):
    engine = object()
    calls = []

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_initialized_engine_key", None)

    def initialize():
        time.sleep(0.02)
        calls.append(1)

    monkeypatch.setattr(database, "_initialize_database", initialize)

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(lambda _: database.init_database(), range(36)))

    assert len(calls) == 1


def test_init_database_reinitializes_after_engine_replacement(monkeypatch):
    calls = []
    monkeypatch.setattr(database, "_initialized_engine_key", None)
    monkeypatch.setattr(database, "_initialize_database", lambda: calls.append(1))
    monkeypatch.setattr(database, "engine", object())

    database.init_database()
    database.init_database()
    assert len(calls) == 1

    monkeypatch.setattr(database, "engine", object())
    database.init_database()
    assert len(calls) == 2


def test_failed_initialization_can_retry(monkeypatch):
    attempts = []
    monkeypatch.setattr(database, "engine", object())
    monkeypatch.setattr(database, "_initialized_engine_key", None)

    def initialize():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("migration failed")

    monkeypatch.setattr(database, "_initialize_database", initialize)

    import pytest

    with pytest.raises(RuntimeError, match="migration failed"):
        database.init_database()

    database.init_database()
    assert len(attempts) == 2


def test_fallback_engine_is_cached_after_rebinding(monkeypatch):
    first = object()
    second = object()
    calls = []
    monkeypatch.setattr(database, "engine", first)
    monkeypatch.setattr(database, "_initialized_engine_key", None)

    def initialize():
        calls.append(1)
        monkeypatch.setattr(database, "engine", second)

    monkeypatch.setattr(database, "_initialize_database", initialize)
    database.init_database()
    database.init_database()
    assert len(calls) == 1
