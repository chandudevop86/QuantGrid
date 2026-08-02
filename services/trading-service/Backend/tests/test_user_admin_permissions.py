from __future__ import annotations

from conftest import admin_headers


def test_admin_can_create_and_list_users(app_client):
    headers = admin_headers(app_client)
    created = app_client.post(
        "/admin/users/create",
        json={"username": "trader1", "password": "TraderPass1!", "role": "trader"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    assert "password" not in created.text.lower()

    listed = app_client.get("/admin/users", headers=headers)
    assert listed.status_code == 200
    assert any(user["username"] == "trader1" for user in listed.json())


def test_non_admin_cannot_create_users(app_client):
    admin = admin_headers(app_client)
    app_client.post(
        "/admin/users/create",
        json={"username": "viewer1", "password": "ViewerPass1!", "role": "viewer"},
        headers=admin,
    )
    login = app_client.post("/auth/login", json={"username": "viewer1", "password": "ViewerPass1!"})
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    blocked = app_client.post(
        "/admin/users/create",
        json={"username": "blocked", "password": "BlockedPass1!", "role": "viewer"},
        headers=viewer_headers,
    )
    assert blocked.status_code == 403
