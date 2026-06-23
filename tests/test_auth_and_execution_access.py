from conftest import TEST_ADMIN_PASSWORD, admin_headers
from starlette.websockets import WebSocketDisconnect
import pytest


def test_valid_login_returns_token_and_dashboard_loads(app_client):
    login = app_client.post(
        "/auth/login",
        json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
    )

    assert login.status_code == 200
    body = login.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"

    dashboard = app_client.get(
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["status"] == "ready"


def test_websocket_requires_authentication(app_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect("/ws") as websocket:
            websocket.receive_json()
    assert exc_info.value.code == 4401


def test_authenticated_websocket_returns_dashboard_status(app_client):
    login = app_client.post(
        "/auth/login",
        json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
    )
    token = login.json()["access_token"]
    with app_client.websocket_connect("/ws", subprotocols=["quantgrid", token]) as websocket:
        websocket.send_text("status")
        for _ in range(20):
            message = websocket.receive_json()
            if message.get("type") == "dashboard_status":
                break
    assert message["type"] == "dashboard_status"
    assert "risk_summary" in message["payload"]


def test_invalid_login_fails_with_error_message(app_client):
    response = app_client.post(
        "/auth/login",
        json={"username": "admin", "password": "WrongPass1!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_viewer_cannot_submit_execution_order(app_client):
    admin = admin_headers(app_client)
    created = app_client.post(
        "/admin/users/create",
        json={"username": "viewer1", "password": "ViewerPass1!", "role": "viewer"},
        headers=admin,
    )
    assert created.status_code == 200

    login = app_client.post(
        "/auth/login",
        json={"username": "viewer1", "password": "ViewerPass1!"},
    )
    assert login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = app_client.post(
        "/execution/order",
        json={
            "strategy_name": "manual",
            "symbol": "NIFTY",
            "side": "BUY",
            "entry_price": 22500,
            "stop_loss": 22450,
            "target_price": 22600,
            "signal_time": "2026-05-27T09:15:00Z",
            "metadata": {"quantity": 1},
        },
        headers=viewer_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User lacks trade_execute permission."
