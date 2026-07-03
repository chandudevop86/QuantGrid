from __future__ import annotations

from conftest import admin_headers


def test_dashboard_operations_returns_decision_contract(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/dashboard/operations", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    decision = payload["decision"]
    assert decision["market_bias"] in {"Bullish", "Bearish", "Neutral"}
    assert decision["trade_recommendation"] in {"Buy CE", "Buy PE", "No Trade"}
    assert isinstance(decision["confidence"], int)
    assert decision["entry_zone"]
    assert decision["stop_loss"]
    assert decision["target"]
    assert decision["risk_level"]
    assert decision["simple_explanation"]
    assert decision["system_status"] in {"Ready", "Caution"}
    assert "market_status" in payload
    assert "risk_summary" in payload
    assert "system_health" in payload
