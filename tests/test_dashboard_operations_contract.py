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
        "data_quality",
        "market_regime",
        "strategy_selection",
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
        "selected_strategy",
        "strategy_version",
        "strategy",
        "trade_quality",
        "confidence_score",
        "probability_score",
        "confidence_label",
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
        "strategy_selection",
        "probability_engine",
        "block_reasons",
        "no_trade_intelligence",
        "explainability",
        "invalidation_level",
        "system_status",
        "trade_eligibility",
        "trade_plan",
        "trade_confidence",
    }
    assert final_decision["trade_decision"] in {"Buy CE", "Buy PE", "No Trade"}
    assert final_decision["trade_quality"] in {"Excellent", "Good", "Average", "Poor", "Skip"}
    assert isinstance(final_decision["selected_strategy"], str)
    assert isinstance(final_decision["strategy_version"], str)
    assert final_decision["confidence_label"] in {"High", "Medium", "Low", "Blocked"}
    assert isinstance(final_decision["no_trade_intelligence"], dict)
    assert isinstance(final_decision["trade_eligibility"], dict)
    assert final_decision["trade_confidence"]["score"] == final_decision["confluence_score"]
    assert isinstance(final_decision["trade_confidence"]["factors"], list)
    assert final_decision["trade_eligibility"]["status"] in {"ELIGIBLE", "BLOCKED"}
    if final_decision["trade_eligibility"]["eligible"]:
        assert isinstance(final_decision["trade_plan"], dict)
    else:
        assert final_decision["trade_plan"] is None
    assert "suggested_action" in final_decision["no_trade_intelligence"]
    assert "next_review_condition" in final_decision["no_trade_intelligence"]
    assert "reason_details" in final_decision["no_trade_intelligence"]
    assert isinstance(final_decision["explainability"], dict)
    assert final_decision["explainability"]["plain_english"]
    assert isinstance(final_decision["strategy_selection"], dict)
    assert isinstance(final_decision["probability_engine"], dict)
    assert isinstance(decision["recommendation_metrics"], dict)
    assert "market_status" in payload
    assert "risk_summary" in payload
    assert "system_health" in payload
    broker = payload["system_health"]["broker"]
    assert isinstance(broker["configured"], bool)
    assert broker["connected"] is False
    assert broker["session_verified"] is False
    worker = payload["system_health"]["background_worker"]
    assert worker["healthy"] is False
    assert worker["status"] == "UNKNOWN"
    assert payload["observability"]["signal_generation_metrics"] is None
    assert payload["observability"]["rejected_order_count"] is None
    assert payload["backtest_context"]["historical_win_rate"] is None
    assert payload["backtest_context"]["sharpe_ratio"] is None
    assert payload["observability"]["api_latency_ms"] >= 0
    assert payload["observability"]["api_latency_status"] in {"OK", "SLOW"}
    assert isinstance(payload["observability"]["decision_metrics"], dict)


def test_dashboard_database_failure_does_not_expose_exception_details(app_client, monkeypatch):
    from Backend.presentation.api import dashboard_api

    secret_detail = "postgresql://quant:super-secret@internal-db:5432/quantgrid"

    def failed_session():
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(dashboard_api, "SessionLocal", failed_session)
    response = app_client.get("/dashboard/operations", headers=admin_headers(app_client))

    assert response.status_code == 200
    payload = response.json()
    db_health = payload["system_health"]["db"]
    assert db_health["healthy"] is False
    assert db_health["status"] == "UNAVAILABLE"
    assert secret_detail not in response.text
    assert "super-secret" not in response.text
