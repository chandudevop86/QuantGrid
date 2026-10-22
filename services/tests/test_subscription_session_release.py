"""Subscription lookups must release checked-out connections before endpoints run."""


def test_subscription_access_closes_db_before_return(monkeypatch):
    from Backend.application import subscriptions

    events = []
    user = type("UserStub", (), {"id": 17, "role": "viewer"})()
    snapshot = {"plan_code": "free", "entitlements": [], "limits": {}}

    class Session:
        def __enter__(self):
            events.append("checkout")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("checkin")

    def load(db, actual_user):
        assert actual_user is user
        events.append("read")
        return snapshot

    monkeypatch.setattr(subscriptions, "SessionLocal", Session)
    monkeypatch.setattr(subscriptions, "subscription_for_user", load)

    access = subscriptions.subscription_access(user=user)
    assert events == ["checkout", "read", "checkin"]
    assert access.user is user
    assert access.snapshot is snapshot


def test_subscription_access_closes_db_on_lookup_failure(monkeypatch):
    from Backend.application import subscriptions
    import pytest

    events = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("checkin")

    def fail(db, user):
        raise RuntimeError("lookup failed")

    monkeypatch.setattr(subscriptions, "SessionLocal", Session)
    monkeypatch.setattr(subscriptions, "subscription_for_user", fail)
    with pytest.raises(RuntimeError, match="lookup failed"):
        subscriptions.subscription_access(user=object())
    assert events == ["checkin"]
