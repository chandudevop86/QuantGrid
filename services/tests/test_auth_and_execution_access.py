from conftest import TEST_ADMIN_PASSWORD, admin_headers, reset_backend_modules
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


def test_live_analysis_job_completes_without_external_worker(app_client, monkeypatch):
    from Backend.application import worker

    monkeypatch.setattr(worker, "run_live_analysis", lambda payload: {"symbol": payload.symbol, "signals": []})
    headers = admin_headers(app_client)

    response = app_client.post(
        "/dashboard/live-analysis/jobs",
        headers=headers,
        json={
            "symbol": "NIFTY",
            "interval": "1m",
            "period": "1d",
            "strategy": "breakout",
            "capital": 100000,
            "risk_pct": 1,
            "rr_ratio": 2,
            "auto_trade": False,
            "execution_mode": "paper",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["result"]["symbol"] == "NIFTY"


def test_websocket_requires_authentication_in_production(app_client, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ALLOW_ANONYMOUS_WEBSOCKET", "false")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect("/ws") as websocket:
            websocket.receive_json()
    assert exc_info.value.code == 4401


def test_websocket_rejects_local_dev_without_token_by_default(app_client, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.delenv("QUANTGRID_ALLOW_ANONYMOUS_WEBSOCKET", raising=False)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect("/ws") as websocket:
            websocket.receive_json()
    assert exc_info.value.code == 4401


def test_websocket_allows_anonymous_only_when_explicitly_enabled(app_client, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_ALLOW_ANONYMOUS_WEBSOCKET", "true")

    with app_client.websocket_connect("/ws") as websocket:
        websocket.send_text("status")
        for _ in range(20):
            message = websocket.receive_json()
            if message.get("type") == "dashboard_status":
                break
    assert message["type"] == "dashboard_status"


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


def test_private_network_dev_cors_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("QUANTGRID_ALLOW_PRIVATE_DEV_CORS", raising=False)
    reset_backend_modules()

    from Backend.presentation.api.main import _allowed_origin_regex

    assert _allowed_origin_regex() == r"^http://(localhost|127\.0\.0\.1):(517[3-9])$"
    reset_backend_modules()


def test_private_network_dev_cors_can_be_enabled_for_lan_testing(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_ALLOW_PRIVATE_DEV_CORS", "true")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    reset_backend_modules()

    from Backend.presentation.api.main import _allowed_origin_regex

    assert "10\\." in (_allowed_origin_regex() or "")
    reset_backend_modules()


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
