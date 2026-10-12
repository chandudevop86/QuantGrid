from __future__ import annotations

from types import SimpleNamespace

from conftest import make_admin_headers


def test_live_execution_is_blocked_when_disabled(app_client):
    headers = make_admin_headers(app_client)
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


def test_live_execution_requires_broker_credentials(app_client, monkeypatch):
    import Backend.presentation.api.execution as execution_api

    monkeypatch.setattr(
        execution_api,
        "get_settings",
        lambda: SimpleNamespace(live_trading_enabled=True, broker_configured=False),
    )

    headers = make_admin_headers(app_client)
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
    assert response.json()["detail"] == "Live trading requires broker credentials."


def test_legacy_production_execute_trade_requires_auth(app_client):
    response = app_client.post(
        "/execute-trade",
        json={
            "signal": {
                "strategy_name": "test",
                "symbol": "NIFTY",
                "side": "BUY",
                "entry_price": 22500,
                "stop_loss": 22450,
                "target_price": 22600,
                "signal_time": "2026-05-20T05:00:00Z",
                "metadata": {"quantity": 1},
            }
        },
    )

    assert response.status_code == 401


def test_legacy_production_execute_trade_is_disabled_for_trader(app_client):
    headers = make_admin_headers(app_client)
    response = app_client.post(
        "/execute-trade",
        json={
            "signal": {
                "strategy_name": "test",
                "symbol": "NIFTY",
                "side": "BUY",
                "entry_price": 22500,
                "stop_loss": 22450,
                "target_price": 22600,
                "signal_time": "2026-05-20T05:00:00Z",
                "metadata": {"quantity": 1},
            }
        },
        headers=headers,
    )

    assert response.status_code == 410


def test_broker_failure_logging_exception_preserves_reconciliation_transition():
    """A logging failure must not interrupt unknown-outcome reconciliation."""
    import ast
    from pathlib import Path

    execution_path = (
        Path(__file__).resolve().parents[1]
        / "trading-service/Backend/presentation/api/execution.py"
    )
    tree = ast.parse(execution_path.read_text())

    place_order = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "place_order"
    )

    protected_handler = None
    for handler in (
        node for node in ast.walk(place_order)
        if isinstance(node, ast.ExceptHandler)
    ):
        for statement in handler.body:
            if not isinstance(statement, ast.Try):
                continue
            calls = [
                node.func.id
                for node in ast.walk(statement)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
            ]
            if "record_broker_failure" in calls:
                protected_handler = statement
                break

    assert protected_handler is not None

    events = []

    def failing_record(**kwargs):
        events.append("logging_attempted")
        raise OSError("simulated audit storage failure")

    def transition(*args, **kwargs):
        events.append("reconciliation_transition")
        return {"status": args[1]}

    class FakeLogger:
        def exception(self, *args, **kwargs):
            events.append("logging_error_reported")

    class FakeLogging:
        @staticmethod
        def getLogger(name):
            return FakeLogger()

    # Execute only the isolated failure-recording try/except.
    isolated = ast.Module(body=[protected_handler], type_ignores=[])
    ast.fix_missing_locations(isolated)

    class Signal:
        symbol = "NIFTY"
        side = "BUY"

    namespace = {
        "record_broker_failure": failing_record,
        "logging": FakeLogging(),
        "exc": RuntimeError("broker outcome unknown"),
        "db": None,
        "actor": None,
        "request": None,
        "signal": Signal(),
        "__name__": "test_execution_failure_handler",
    }

    exec(compile(isolated, str(execution_path), "exec"), namespace)

    assert events == [
        "logging_attempted",
        "logging_error_reported",
    ]

    # Confirm that the real handler places reconciliation immediately after it.
    parent_handler = next(
        handler
        for handler in ast.walk(place_order)
        if isinstance(handler, ast.ExceptHandler)
        and protected_handler in handler.body
    )
    next_statement = parent_handler.body[
        parent_handler.body.index(protected_handler) + 1
    ]
    assert isinstance(next_statement, ast.Assign)
    assert isinstance(next_statement.value, ast.Call)
    assert isinstance(next_statement.value.func, ast.Name)
    assert next_statement.value.func.id == "_transition_lifecycle_order"

    transition({}, "reconciliation_required")
    assert events[-1] == "reconciliation_transition"


def test_live_broker_and_failure_logger_exceptions_keep_durable_reconciliation(
    app_client, monkeypatch
):
    """An ambiguous broker outcome remains blocked despite failure logging errors."""
    from sqlalchemy import text

    import Backend.presentation.api.execution as execution_api
    from Backend.application.subscriptions import subscription_access
    from Backend.core.database import SessionLocal
    from Backend.presentation.api.main import app

    broker_calls = []

    class FakeBroker:
        supports_protected_order_submission = True
        supports_broker_native_protective_stop = True

        async def place_protected_order(self, order):
            broker_calls.append(order)
            raise TimeoutError("simulated ambiguous broker timeout")

    class FakeAccess:
        snapshot = {"plan_code": "test"}

        def can(self, feature):
            return True

    def fail_recording(**kwargs):
        raise OSError("simulated broker failure logging error")

    monkeypatch.setattr(
        execution_api,
        "get_settings",
        lambda: SimpleNamespace(
            live_trading_enabled=True,
            broker_live_enabled=True,
            broker_configured=True,
        ),
    )
    monkeypatch.setattr(
        execution_api,
        "broker_client_for_mode",
        lambda mode: FakeBroker(),
    )
    monkeypatch.setattr(
        execution_api,
        "record_broker_failure",
        fail_recording,
    )
    monkeypatch.setattr(
        execution_api,
        "_request_is_https",
        lambda request: True,
    )
    monkeypatch.setattr(
        execution_api,
        "_execution_qualification",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        execution_api,
        "_live_guardrail_failure",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        execution_api,
        "validate_order_risk",
        lambda *args, **kwargs: SimpleNamespace(
            allowed=True,
            reason="approved",
        ),
    )
    monkeypatch.setattr(
        execution_api,
        "latest_candles",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        execution_api,
        "_audit_risk_decision",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        execution_api,
        "_audit_execution_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        execution_api,
        "alert_execution_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        execution_api,
        "write_audit_log",
        lambda *args, **kwargs: None,
    )

    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[subscription_access] = lambda: FakeAccess()

    payload = {
        "strategy_name": "BROKER_LOGGER_REGRESSION",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 22500,
        "stop_loss": 22450,
        "target_price": 22600,
        "signal_time": "2026-05-20T05:00:00Z",
        "metadata": {"quantity": 1},
    }

    headers = make_admin_headers(app_client)
    headers["X-QuantGrid-Mode"] = "live"

    try:
        first = app_client.post(
            "/execution/order",
            json=payload,
            headers=headers,
        )

        assert first.status_code == 200, first.text
        assert first.json()["status"] == "reconciliation_required"
        assert len(broker_calls) == 1

        with SessionLocal() as db:
            orders = db.execute(
                text(
                    "SELECT local_order_id, status FROM orders "
                    "WHERE order_key = :key"
                ),
                {"key": "NIFTY:BUY:BROKER_LOGGER_REGRESSION"},
            ).all()

            assert len(orders) == 1
            assert orders[0][1] == "reconciliation_required"

            intents = db.execute(
                text(
                    "SELECT local_order_id, status "
                    "FROM broker_submission_intents "
                    "WHERE logical_key = :key"
                ),
                {"key": "NIFTY:BUY:BROKER_LOGGER_REGRESSION"},
            ).all()

            assert len(intents) == 1
            assert intents[0][0] == orders[0][0]
            assert intents[0][1] == "reconciliation_required"

        # A repeated logical order must return a controlled rejection.
        second = app_client.post(
            "/execution/order",
            json=payload,
            headers=headers,
        )
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "rejected"
        assert "DUPLICATE_ACTIVE_ORDER" in second.json()["reason"]
        assert second.json()["broker_confirmed"] is False
        assert len(broker_calls) == 1

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
