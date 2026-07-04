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
    assert "checklist_score" in decision["factor_snapshot"]
    checklist = decision["factor_snapshot"]["checklist"]
    assert set(checklist) == {
        "checklist_score",
        "passed",
        "failed",
        "warnings",
        "trend",
        "ema",
        "volume",
        "support_resistance",
        "risk_reward",
        "htf",
        "market_structure",
        "key_levels",
        "fvg",
        "price_action",
        "options_flow",
        "institutional",
        "discipline",
        "confluence_engine",
        "confidence_engine",
        "market_regime",
        "supply_demand",
        "liquidity",
    }
    assert isinstance(checklist["passed"], list)
    assert isinstance(checklist["failed"], list)
    assert isinstance(checklist["warnings"], list)
    assert "trend_analysis" in decision["factor_snapshot"]
    assert "ema_analysis" in decision["factor_snapshot"]
    assert "volume_analysis" in decision["factor_snapshot"]
    assert "support_resistance" in decision["factor_snapshot"]
    assert "risk_reward" in decision["factor_snapshot"]
    assert "high_probability_trade_engine" in decision["factor_snapshot"]
    gate = decision["factor_snapshot"]["high_probability_trade_engine"]["paper_trade_gate"]
    assert isinstance(gate["allowed"], bool)
    assert gate["status"] in {"Allowed", "Blocked"}
    assert isinstance(gate["reasons"], list)
    final_decision = decision["factor_snapshot"]["final_decision"]
    assert set(final_decision) == {
        "market_bias",
        "trade_decision",
        "trade_quality",
        "confidence_score",
        "confluence_score",
        "entry_zone",
        "stop_loss",
        "target",
        "risk_reward_ratio",
        "position_size",
        "risk_level",
        "explanation",
        "supporting_factors",
        "opposing_factors",
        "block_reasons",
        "invalidation_level",
        "system_status",
    }
    assert final_decision["trade_decision"] in {"Buy CE", "Buy PE", "No Trade"}
    assert final_decision["trade_quality"] in {"Excellent", "Good", "Average", "Poor", "Skip"}
    assert isinstance(decision["recommendation_metrics"], dict)
    assert "market_status" in payload
    assert "risk_summary" in payload
    assert "system_health" in payload
    assert payload["observability"]["api_latency_ms"] >= 0
    assert payload["observability"]["api_latency_status"] in {"OK", "SLOW"}
    assert isinstance(payload["observability"]["decision_metrics"], dict)
