from __future__ import annotations

from types import SimpleNamespace

from conftest import admin_headers


def test_broker_circuit_breaker_activates_after_threshold(tmp_path, monkeypatch):
    from Backend.application import broker_circuit_breaker

    monkeypatch.setattr(broker_circuit_breaker, "STATUS_FILE", tmp_path / "broker_circuit.json")
    monkeypatch.setenv("BROKER_FAILURE_WINDOW_SECONDS", "120")
    monkeypatch.setenv("BROKER_FAILURE_THRESHOLD", "3")
    monkeypatch.setenv("BROKER_CIRCUIT_COOLDOWN_SECONDS", "300")
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(broker_circuit_breaker, "send_alert", lambda subject, message: alerts.append((subject, message)))

    assert broker_circuit_breaker.record_broker_failure(reason="timeout")["active"] is False
    assert broker_circuit_breaker.record_broker_failure(reason="timeout")["active"] is False
    status = broker_circuit_breaker.record_broker_failure(reason="timeout")

    assert status["active"] is True
    assert status["failure_count"] == 3
    assert status["failure_threshold"] == 3
    assert alerts
    assert "broker circuit breaker active" in alerts[0][0].lower()


def test_broker_circuit_breaker_reset_clears_failures(tmp_path, monkeypatch):
    from Backend.application import broker_circuit_breaker

    monkeypatch.setattr(broker_circuit_breaker, "STATUS_FILE", tmp_path / "broker_circuit.json")
    monkeypatch.setenv("BROKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setattr(broker_circuit_breaker, "send_alert", lambda *_args, **_kwargs: None)

    assert broker_circuit_breaker.record_broker_failure(reason="broker down")["active"] is True
    status = broker_circuit_breaker.reset_broker_circuit(actor="admin")

    assert status["active"] is False
    assert status["failure_count"] == 0


def test_live_guardrail_rejects_active_broker_circuit(monkeypatch):
    from Backend.presentation.api import execution as execution_api

    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(
        execution_api,
        "broker_circuit_status",
        lambda: {"active": True, "reason": "Broker failure threshold reached."},
    )

    request = SimpleNamespace(headers={"x-forwarded-proto": "https"}, url=SimpleNamespace(scheme="https"))
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(
        broker_live_enabled=True,
        risk_engine_enabled=True,
        broker_configured=True,
        broker_provider="mock",
        audit_logging_enabled=True,
        market_data_provider="broker",
        allow_yahoo_for_live=False,
    )
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})

    reason = execution_api._live_guardrail_failure(
        request=request,
        actor=actor,
        settings=settings,
        candles_1m=[{"close": 100}],
        risk_decision=risk,
    )

    assert reason and reason.startswith("Broker circuit breaker active")


def test_broker_circuit_breaker_apis_and_admin_reset(app_client, tmp_path, monkeypatch):
    import Backend.application.broker_circuit_breaker as breaker

    monkeypatch.setattr(breaker, "STATUS_FILE", tmp_path / "broker_circuit.json")
    monkeypatch.setenv("BROKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setattr(breaker, "send_alert", lambda *_args, **_kwargs: None)
    breaker.record_broker_failure(reason="broker down")

    headers = admin_headers(app_client)
    status_response = app_client.get("/broker/circuit-breaker/status", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["active"] is True

    reset_response = app_client.post("/broker/circuit-breaker/reset", headers=headers)
    assert reset_response.status_code == 200
    assert reset_response.json()["active"] is False

    unauthorized = app_client.post("/broker/circuit-breaker/reset")
    assert unauthorized.status_code == 401
