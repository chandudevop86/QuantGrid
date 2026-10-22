"""Regression: token verification must not pin a database connection to a long request."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def test_current_user_releases_auth_transaction_before_return(monkeypatch):
    from Backend.presentation.api import auth

    events = []
    user = SimpleNamespace(id=42, username="reader", role="viewer")
    class FakeSession:
        def __enter__(self):
            events.append("open")
            return self
        def get(self, model, uid):
            assert model is auth.User
            assert uid == 42
            events.append("lookup")
            return user
        def expunge(self, value):
            assert value is user
            events.append("detach")
        def __exit__(self, exc_type, exc_value, traceback):
            events.append("closed")
    monkeypatch.setattr(auth, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(auth, "verify_token", lambda _: {"uid": 42})
    result = auth.current_user(authorization="Bearer valid")
    assert result is user
    assert events == ["open", "lookup", "detach", "closed"]


def test_current_user_rejects_missing_token_without_db_checkout(monkeypatch):
    from Backend.presentation.api import auth
    monkeypatch.setattr(auth, "SessionLocal", lambda: pytest.fail("DB should not be opened"))
    with pytest.raises(HTTPException) as exc:
        auth.current_user(authorization=None)
    assert exc.value.status_code == 401


def test_current_user_closes_session_for_deleted_user(monkeypatch):
    from Backend.presentation.api import auth
    events = []
    class FakeSession:
        def __enter__(self):
            return self
        def get(self, model, uid):
            return None
        def __exit__(self, *_):
            events.append("closed")
    monkeypatch.setattr(auth, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(auth, "verify_token", lambda _: {"uid": 99})
    with pytest.raises(HTTPException) as exc:
        auth.current_user(authorization="Bearer valid")
    assert exc.value.status_code == 401
    assert events == ["closed"]
