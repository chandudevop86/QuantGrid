from __future__ import annotations

from conftest import admin_headers


def test_subscription_plans_and_default_free_account(app_client):
    headers = admin_headers(app_client)

    plans = app_client.get("/subscriptions/plans")
    mine = app_client.get("/subscriptions/me", headers=headers)

    assert plans.status_code == 200
    assert [item["code"] for item in plans.json()["plans"]] == ["free", "starter", "pro", "institutional"]
    assert plans.json()["billing_provider_configured"] is False
    assert mine.status_code == 200
    assert mine.json()["plan_code"] == "free"
    assert mine.json()["effective_status"] == "active"
    assert "dashboard" in mine.json()["features"]


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
    assert "backtesting" in assigned.json()["features"]
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
