from __future__ import annotations

from conftest import admin_headers


def test_subscription_plans_and_default_free_account(app_client):
    headers = admin_headers(app_client)

    plans = app_client.get("/subscriptions/plans")
    mine = app_client.get("/subscriptions/me", headers=headers)

    assert plans.status_code == 200
    assert [item["code"] for item in plans.json()["plans"]] == ["free", "basic", "pro", "premium"]
    assert plans.json()["billing_provider_configured"] is False
    assert mine.status_code == 200
    assert mine.json()["plan_code"] == "admin"
    assert mine.json()["effective_status"] == "active"
    assert "admin.subscriptions" in mine.json()["entitlements"]


def test_admin_can_assign_subscription_and_assignment_is_audited(app_client):
    headers = admin_headers(app_client)
    created = app_client.post(
        "/admin/users/create",
        json={"username": "subscriber", "password": "Subscriber1!", "role": "trader"},
        headers=headers,
    )
    assert created.status_code == 200
    user_id = created.json()["id"]

    assigned = app_client.put(
        f"/subscriptions/admin/users/{user_id}",
        json={"plan_code": "pro", "status": "trialing", "period_days": 14},
        headers=headers,
    )

    assert assigned.status_code == 200
    assert assigned.json()["plan_code"] == "pro"
    assert assigned.json()["effective_status"] == "trialing"
    assert "backtest.basic" in assigned.json()["entitlements"]
    assert assigned.json()["current_period_end"]

    audit = app_client.get("/audit/logs", headers=headers).json()["events"]
    assert any(item["action"] == "Subscription updated" and str(item["target_id"]) == str(user_id) for item in audit)


def test_non_admin_cannot_assign_subscription(app_client):
    headers = admin_headers(app_client)
    created = app_client.post(
        "/admin/users/create",
        json={"username": "basic-user", "password": "BasicUser1!", "role": "trader"},
        headers=headers,
    ).json()
    login = app_client.post("/auth/login", json={"username": "basic-user", "password": "BasicUser1!"})
    trader = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = app_client.put(
        f"/subscriptions/admin/users/{created['id']}",
        json={"plan_code": "institutional", "status": "active", "period_days": 30},
        headers=trader,
    )

    assert response.status_code == 403


def test_public_signup_creates_only_a_free_viewer_account(app_client):
    response = app_client.post("/auth/register", json={"username": "new-subscriber", "password": "Subscriber1!"})
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    mine = app_client.get("/subscriptions/me", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["plan_code"] == "free"
    assert "live_trade.execute" not in mine.json()["entitlements"]
    duplicate = app_client.post("/auth/register", json={"username": "new-subscriber", "password": "Subscriber1!"})
    assert duplicate.status_code == 409


def _create_user_headers(app_client, username: str) -> tuple[int, dict[str, str]]:
    admin = admin_headers(app_client)
    created = app_client.post("/admin/users/create", json={"username": username, "password": "Subscriber1!", "role": "trader"}, headers=admin)
    login = app_client.post("/auth/login", json={"username": username, "password": "Subscriber1!"})
    return created.json()["id"], {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_free_user_direct_api_call_is_rejected_and_pro_is_allowed(app_client):
    user_id, user_headers = _create_user_headers(app_client, "entitlement-user")
    denied = app_client.get("/modules/risk-engine", headers=user_headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["error"] == "subscription_required"
    app_client.put(f"/subscriptions/admin/users/{user_id}", json={"plan_code": "pro", "status": "active", "period_days": 30}, headers=admin_headers(app_client))
    allowed = app_client.get("/modules/risk-engine", headers=user_headers)
    assert allowed.status_code == 200


def test_expired_subscription_falls_back_and_temporary_override_works(app_client):
    user_id, user_headers = _create_user_headers(app_client, "expired-user")
    admin = admin_headers(app_client)
    app_client.put(f"/subscriptions/admin/users/{user_id}", json={"plan_code": "pro", "status": "expired", "period_days": 30}, headers=admin)
    assert app_client.get("/modules/risk-engine", headers=user_headers).status_code == 403
    app_client.put(f"/subscriptions/admin/users/{user_id}", json={"plan_code": "free", "status": "active", "period_days": 30}, headers=admin)
    override = app_client.post(f"/subscriptions/admin/users/{user_id}/overrides", json={"entitlement_key": "risk.advanced", "enabled": True, "reason": "Approved support test"}, headers=admin)
    assert override.status_code == 200
    assert "risk.advanced" in override.json()["entitlements"]
    assert app_client.get("/modules/risk-engine", headers=user_headers).status_code == 200
