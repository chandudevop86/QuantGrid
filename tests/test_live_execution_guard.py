from __future__ import annotations

from conftest import admin_headers


def test_live_execution_is_blocked_when_disabled(app_client):
    headers = admin_headers(app_client)
    headers["X-QuantGrid-Mode"] = "live"
    response = app_client.post(
        "/execution/order",
        json={
            "strategy_name": "test",
            "symbol": "NIFTY",
            "side": "BUY",
            "entry_price": 22500,
            "stop_loss": 22450,
            "target_price": 22600,
            "signal_time": "2026-05-20T05:00:00Z",
            "metadata": {"quantity": 1},
        },
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Live trading is disabled. Paper trading only."
