from __future__ import annotations


def test_login_rate_limit(app_client):
    for _ in range(5):
        response = app_client.post("/auth/login", json={"username": "admin", "password": "WrongPass1!"})
        assert response.status_code == 401

    limited = app_client.post("/auth/login", json={"username": "admin", "password": "WrongPass1!"})
    assert limited.status_code == 429
