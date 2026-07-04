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
    assert decision["system_status"] in {"LIVE", "DEGRADED", "STALE", "CLOSED"}
    assert decision["data_status"] in {"LIVE", "DEGRADED", "STALE", "CLOSED"}
    assert isinstance(decision["blocked"], bool)
    assert isinstance(decision["supporting_factors"], list)
    assert isinstance(decision["opposing_factors"], list)
    assert isinstance(decision["warnings"], list)
    assert decision["invalidation_level"]
    assert isinstance(decision["score_breakdown"], list)
    assert decision["score_reason"]
    assert "decision_id" in decision
    assert isinstance(decision["factor_snapshot"], dict)
    assert isinstance(decision["recommendation_metrics"], dict)
    assert "market_status" in payload
    assert "risk_summary" in payload
    assert "system_health" in payload
    assert payload["observability"]["api_latency_ms"] >= 0
    assert payload["observability"]["api_latency_status"] in {"OK", "SLOW"}
    assert isinstance(payload["observability"]["decision_metrics"], dict)
