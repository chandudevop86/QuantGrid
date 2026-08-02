from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_ADMIN_PASSWORD, TEST_SECRET, admin_headers, reset_backend_modules
from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def _signal(**overrides):
    from Backend.domain.models.signal import StrategySignal

    values = {
        "strategy_name": "safety",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target_price": 110.0,
        "signal_time": datetime.now(timezone.utc),
        "metadata": {"quantity": 1, "score": 20, "validation_passed": True},
    }
    values.update(overrides)
    return StrategySignal(**values)


def _fresh_candle(close: float = 100.0) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 100,
        }
    ]


def _risk_status(**overrides: Any) -> dict[str, Any]:
    values = {
        "daily_pnl": 0.0,
        "max_daily_loss": 1000.0,
        "trades_today": 0,
        "max_trades_per_day": 10,
        "consecutive_losses": 0,
        "max_consecutive_losses": 3,
        "open_positions": 0,
        "max_open_positions": 5,
        "max_quantity": 100,
        "risk_per_trade_amount": 100.0,
        "risk_configured": True,
    }
    values.update(overrides)
    return values


def _valid_candle_result() -> SimpleNamespace:
    return SimpleNamespace(valid=True, valid_for_analysis=True, valid_for_execution=True, market_status="LIVE MARKET", model_dump=lambda: {})


def _stale_candle_result() -> SimpleNamespace:
    return SimpleNamespace(valid=False, valid_for_analysis=False, valid_for_execution=False, market_status="DELAYED FEED", model_dump=lambda: {})


@contextmanager
def _app_client(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_ALLOW_DEV_SEED_USERS", "true")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_USERS", f"admin:{TEST_ADMIN_PASSWORD}:admin")
    reset_backend_modules()
    from Backend.presentation.api.main import app

    with TestClient(app) as client:
        from Backend.core.database import SessionLocal
        from Backend.domain.security.models import User
        from Backend.domain.security.passwords import hash_password

        with SessionLocal() as db:
            db.add(User(username="admin", password_hash=hash_password(TEST_ADMIN_PASSWORD), role="admin"))
            db.commit()
        yield client
    reset_backend_modules()


def _role_headers(client, admin: dict[str, str], username: str, role: str) -> dict[str, str]:
    password = f"{role.title()}SafetyPass1!"
    created = client.post(
        "/admin/users/create",
        json={"username": username, "password": password, "role": role},
        headers=admin,
    )
    assert created.status_code == 200, created.text
    login = client.post("/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_risk_engine_rejects_missing_stop_loss(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    result = risk_gate.validate_order_risk(_signal(stop_loss=0), execution_mode="paper", candles_1m=_fresh_candle())
    assert result.allowed is False
    assert result.reason == "STOP_LOSS_REQUIRED"


def test_risk_engine_rejects_missing_target(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    result = risk_gate.validate_order_risk(_signal(target_price=0), execution_mode="paper", candles_1m=_fresh_candle())
    assert result.allowed is False
    assert result.reason == "TARGET_REQUIRED"


def test_risk_engine_rejects_max_risk_per_trade_exceeded(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status(risk_per_trade_amount=10))
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    result = risk_gate.validate_order_risk(_signal(stop_loss=50, metadata={"quantity": 1, "score": 20}), execution_mode="paper", candles_1m=_fresh_candle())
    assert result.allowed is False
    assert result.reason == "MAX_RISK_PER_TRADE_EXCEEDED"


def test_risk_engine_rejects_max_daily_loss_exceeded(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status(daily_pnl=-1000, max_daily_loss=1000))
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    result = risk_gate.validate_order_risk(_signal(), execution_mode="paper", candles_1m=_fresh_candle())
    assert result.allowed is False
    assert result.reason == "MAX_DAILY_LOSS_EXCEEDED"


def test_risk_engine_rejects_stale_market_data(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    stale = [{**_fresh_candle()[0], "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()}]
    result = risk_gate.validate_order_risk(_signal(), execution_mode="live", candles_1m=stale)
    assert result.allowed is False
    assert result.reason.startswith("STALE_MARKET_DATA")


def test_risk_engine_rejects_kill_switch_active(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": True, "reason": "test"})
    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    result = risk_gate.validate_order_risk(_signal(), execution_mode="paper", candles_1m=_fresh_candle())
    assert result.allowed is False
    assert result.reason.startswith("KILL_SWITCH_ACTIVE")


def test_risk_engine_allows_valid_paper_order(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    result = risk_gate.validate_order_risk(_signal(), execution_mode="paper", candles_1m=_fresh_candle())
    assert result.allowed is True


def test_order_risk_blocks_wide_spread_from_signal_metadata(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    signal = _signal(metadata={"quantity": 1, "score": 20, "validation_passed": True, "spread_bps": 60})

    result = risk_gate.validate_order_risk(signal, execution_mode="paper", candles_1m=_fresh_candle())

    assert result.allowed is False
    assert result.reason == "SPREAD_TOO_WIDE"


def test_order_risk_blocks_high_impact_news_from_signal_metadata(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    signal = _signal(metadata={"quantity": 1, "score": 20, "validation_passed": True, "high_impact_news": True})

    result = risk_gate.validate_order_risk(signal, execution_mode="paper", candles_1m=_fresh_candle())

    assert result.allowed is False
    assert result.reason == "NEWS_RISK"


def test_order_risk_blocks_portfolio_exposure_from_signal_metadata(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status())
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    signal = _signal(
        metadata={
            "quantity": 1,
            "score": 20,
            "validation_passed": True,
            "portfolio_exposure_pct": 75.0,
            "symbol_exposure_pct": 10.0,
            "correlated_positions": 1,
        }
    )

    result = risk_gate.validate_order_risk(signal, execution_mode="paper", candles_1m=_fresh_candle())

    assert result.allowed is False
    assert result.reason == "PORTFOLIO_EXPOSURE_LIMIT"
    assert "PORTFOLIO_EXPOSURE_LIMIT" in result.details["risk_engine"]["blocked_by"]


def test_order_risk_blocks_weekly_loss_from_risk_status(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(
        risk_gate,
        "risk_status",
        lambda: _risk_status(weekly_pnl=-7000.0, max_weekly_loss=7000.0),
    )
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())

    result = risk_gate.validate_order_risk(_signal(), execution_mode="paper", candles_1m=_fresh_candle())

    assert result.allowed is False
    assert result.reason == "WEEKLY_LOSS_LIMIT"
    assert "WEEKLY_LOSS_LIMIT" in result.details["risk_engine"]["blocked_by"]


def test_order_risk_blocks_consecutive_losses_from_risk_status(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(
        risk_gate,
        "risk_status",
        lambda: _risk_status(consecutive_losses=3, max_consecutive_losses=3, weekly_pnl=0.0, max_weekly_loss=7000.0),
    )
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())

    result = risk_gate.validate_order_risk(_signal(), execution_mode="paper", candles_1m=_fresh_candle())

    assert result.allowed is False
    assert result.reason == "MAX_CONSECUTIVE_LOSSES"
    assert "MAX_CONSECUTIVE_LOSSES" in result.details["risk_engine"]["blocked_by"]


def test_live_order_risk_blocks_active_broker_circuit(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status(weekly_pnl=0.0, max_weekly_loss=7000.0))
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    monkeypatch.setattr(
        risk_gate,
        "broker_circuit_status",
        lambda: {"active": True, "reason": "Broker failure threshold reached."},
    )

    result = risk_gate.validate_order_risk(_signal(), execution_mode="live", candles_1m=_fresh_candle())

    assert result.allowed is False
    assert result.reason == "BROKER_CIRCUIT_ACTIVE"
    assert result.details["broker_circuit"]["active"] is True
    assert "BROKER_CIRCUIT_ACTIVE" in result.details["risk_engine"]["blocked_by"]


def test_paper_order_risk_ignores_active_broker_circuit(monkeypatch):
    from Backend.application import risk_gate

    monkeypatch.setattr(risk_gate, "risk_status", lambda: _risk_status(weekly_pnl=0.0, max_weekly_loss=7000.0))
    monkeypatch.setattr(risk_gate, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(risk_gate, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    monkeypatch.setattr(
        risk_gate,
        "broker_circuit_status",
        lambda: {"active": True, "reason": "Broker failure threshold reached."},
    )

    result = risk_gate.validate_order_risk(_signal(), execution_mode="paper", candles_1m=_fresh_candle())

    assert result.allowed is True
    assert result.details["broker_circuit"]["active"] is False
    assert "BROKER_CIRCUIT_ACTIVE" not in result.details["risk_engine"]["blocked_by"]


def test_live_guardrail_rejects_live_order_on_http():
    from Backend.presentation.api.execution import _live_guardrail_failure

    request = SimpleNamespace(headers={}, url=SimpleNamespace(scheme="http"))
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(
        broker_live_enabled=True,
        risk_engine_enabled=True,
        broker_configured=True,
        broker_provider="mock",
        audit_logging_enabled=True,
    )
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})
    assert _live_guardrail_failure(request=request, actor=actor, settings=settings, candles_1m=_fresh_candle(), risk_decision=risk) == "Live trading requires HTTPS."


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({"broker_live_enabled": False}, "Live trading requires BROKER_LIVE_ENABLED=true."),
        ({"broker_configured": False}, "Live trading requires broker credentials."),
    ],
)
def test_live_guardrail_rejects_broker_disabled_or_credentials_missing(settings, expected):
    from Backend.presentation.api import execution as execution_api
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())

    request = SimpleNamespace(
        headers={"x-forwarded-proto": "https"},
        url=SimpleNamespace(scheme="https"),
        client=None,
        state=SimpleNamespace(),
    )
    actor = SimpleNamespace(role="trader")
    base = {
        "broker_live_enabled": True,
        "risk_engine_enabled": True,
        "broker_configured": True,
        "broker_provider": "mock",
        "audit_logging_enabled": True,
    }
    base.update(settings)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})
    try:
        assert execution_api._live_guardrail_failure(request=request, actor=actor, settings=SimpleNamespace(**base), candles_1m=_fresh_candle(), risk_decision=risk) == expected
    finally:
        monkeypatch.undo()


def test_live_guardrail_rejects_market_data_stale():
    from Backend.presentation.api import execution as execution_api
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _stale_candle_result())

    request = SimpleNamespace(
        headers={"x-forwarded-proto": "https"},
        url=SimpleNamespace(scheme="https"),
        client=None,
        state=SimpleNamespace(),
    )
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(broker_live_enabled=True, risk_engine_enabled=True, broker_configured=True, broker_provider="mock", audit_logging_enabled=True)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})
    stale = [{**_fresh_candle()[0], "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()}]
    try:
        reason = execution_api._live_guardrail_failure(request=request, actor=actor, settings=settings, candles_1m=stale, risk_decision=risk)
        assert reason and reason.startswith("Live trading requires fresh market data")
    finally:
        monkeypatch.undo()


def test_live_guardrail_rejects_viewer_role():
    from Backend.presentation.api import execution as execution_api
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())

    request = SimpleNamespace(headers={"x-forwarded-proto": "https"}, url=SimpleNamespace(scheme="https"))
    actor = SimpleNamespace(role="viewer")
    settings = SimpleNamespace(broker_live_enabled=True, risk_engine_enabled=True, broker_configured=True, broker_provider="mock", audit_logging_enabled=True)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})
    try:
        assert execution_api._live_guardrail_failure(request=request, actor=actor, settings=settings, candles_1m=_fresh_candle(), risk_decision=risk) == "Live trading requires trader or admin role."
    finally:
        monkeypatch.undo()


def test_live_guardrail_rejection_writes_audit_log(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import AuditLog, User
    from Backend.presentation.api import execution as execution_api

    init_database()
    request = SimpleNamespace(
        headers={"x-forwarded-proto": "https"},
        url=SimpleNamespace(scheme="https"),
        client=None,
        state=SimpleNamespace(),
    )
    risk = SimpleNamespace(
        allowed=True,
        reason="OK",
        details={"daily_pnl": 0, "max_daily_loss": 1000},
        to_dict=lambda: {"allowed": True, "reason": "OK", "details": {"daily_pnl": 0, "max_daily_loss": 1000}},
    )

    with SessionLocal() as db:
        actor = User(username="trader-audit", password_hash="hash", role="trader")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        actor_id = actor.id

        result = execution_api._reject_live_guardrail(
            db=db,
            request=request,
            actor=actor,
            signal=_signal(),
            reason="Live trading requires HTTPS.",
            execution_mode="live",
            risk_decision=risk,
        )
        audit = db.query(AuditLog).filter(AuditLog.action == "execution_blocked").one()

    assert result["status"] == "rejected"
    assert audit.actor_user_id == actor_id
    assert audit.target_id == "NIFTY"
    assert "Live trading requires HTTPS." in audit.metadata_json


def test_live_guardrail_allows_when_all_checks_pass(monkeypatch):
    from Backend.presentation.api import execution as execution_api

    monkeypatch.setattr(execution_api, "_broker_session_valid", lambda settings: True)
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    request = SimpleNamespace(headers={"x-forwarded-proto": "https"}, url=SimpleNamespace(scheme="https"))
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(broker_live_enabled=True, risk_engine_enabled=True, broker_configured=True, broker_provider="mock", audit_logging_enabled=True)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})
    assert execution_api._live_guardrail_failure(request=request, actor=actor, settings=settings, candles_1m=_fresh_candle(), risk_decision=risk) is None


def test_live_guardrail_rejects_app_managed_stops_by_default(monkeypatch):
    from Backend.presentation.api import execution as execution_api

    monkeypatch.delenv("QUANTGRID_ALLOW_APP_MANAGED_STOPS", raising=False)
    monkeypatch.setattr(execution_api, "_broker_session_valid", lambda settings: True)
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    request = SimpleNamespace(headers={"x-forwarded-proto": "https"}, url=SimpleNamespace(scheme="https"))
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(broker_live_enabled=True, risk_engine_enabled=True, broker_configured=True, broker_provider="mock", audit_logging_enabled=True)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})

    reason = execution_api._live_guardrail_failure(
        request=request,
        actor=actor,
        settings=settings,
        candles_1m=_fresh_candle(),
        risk_decision=risk,
        signal=_signal(),
    )

    assert reason and reason.startswith("Live trading requires broker-native stop protection")


def test_live_guardrail_allows_app_managed_stops_when_explicitly_enabled(monkeypatch):
    from Backend.presentation.api import execution as execution_api

    monkeypatch.setenv("QUANTGRID_ALLOW_APP_MANAGED_STOPS", "true")
    monkeypatch.setenv("QUANTGRID_EXIT_MONITOR_ENABLED", "true")
    monkeypatch.setenv("QUANTGRID_EXIT_MONITOR_MODE", "live")
    monkeypatch.setenv("QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS", "5")
    monkeypatch.setattr(execution_api, "_broker_session_valid", lambda settings: True)
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    request = SimpleNamespace(headers={"x-forwarded-proto": "https"}, url=SimpleNamespace(scheme="https"))
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(broker_live_enabled=True, risk_engine_enabled=True, broker_configured=True, broker_provider="mock", audit_logging_enabled=True)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})

    assert execution_api._live_guardrail_failure(
        request=request,
        actor=actor,
        settings=settings,
        candles_1m=_fresh_candle(),
        risk_decision=risk,
        signal=_signal(),
    ) is None


@pytest.mark.parametrize(
    ("enabled", "mode", "interval"),
    [
        ("false", "live", "5"),
        ("true", "paper", "5"),
        ("true", "live", "30"),
    ],
)
def test_live_guardrail_rejects_app_managed_stops_without_live_monitor(monkeypatch, enabled, mode, interval):
    from Backend.presentation.api import execution as execution_api

    monkeypatch.setenv("QUANTGRID_ALLOW_APP_MANAGED_STOPS", "true")
    monkeypatch.setenv("QUANTGRID_EXIT_MONITOR_ENABLED", enabled)
    monkeypatch.setenv("QUANTGRID_EXIT_MONITOR_MODE", mode)
    monkeypatch.setenv("QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS", interval)
    monkeypatch.setattr(execution_api, "_broker_session_valid", lambda settings: True)
    monkeypatch.setattr(execution_api, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: _valid_candle_result())
    request = SimpleNamespace(headers={"x-forwarded-proto": "https"}, url=SimpleNamespace(scheme="https"))
    actor = SimpleNamespace(role="trader")
    settings = SimpleNamespace(broker_live_enabled=True, risk_engine_enabled=True, broker_configured=True, broker_provider="mock", audit_logging_enabled=True)
    risk = SimpleNamespace(allowed=True, reason="OK", details={"daily_pnl": 0, "max_daily_loss": 1000})

    reason = execution_api._live_guardrail_failure(
        request=request,
        actor=actor,
        settings=settings,
        candles_1m=_fresh_candle(),
        risk_decision=risk,
        signal=_signal(),
    )

    assert reason == "Live app-managed stops require QUANTGRID_EXIT_MONITOR_ENABLED=true, QUANTGRID_EXIT_MONITOR_MODE=live, and interval <= 10 seconds."


class FakeKite:
    VARIETY_REGULAR = "regular"

    def __init__(self, *, fail: Exception | None = None, status: str = "COMPLETE") -> None:
        self.fail = fail
        self.status = status
        self.cancelled = False

    def place_order(self, **kwargs):
        if self.fail:
            raise self.fail
        return "kite-order-1"

    def order_history(self, order_id):
        if self.fail:
            raise self.fail
        return [{"tradingsymbol": "NIFTY", "transaction_type": "BUY", "quantity": 2, "price": 100, "status": self.status, "average_price": 101}]

    def cancel_order(self, **kwargs):
        if self.fail:
            raise self.fail
        self.cancelled = True


def test_broker_adapter_place_order_success():
    from Backend.trading_system.broker import ZerodhaBrokerAdapter

    order = asyncio.run(ZerodhaBrokerAdapter(FakeKite()).place_order("NIFTY", "BUY", 2, 100))
    assert order.order_id == "kite-order-1"


def test_broker_adapter_broker_failure():
    from Backend.trading_system.broker import ZerodhaBrokerAdapter

    with pytest.raises(RuntimeError):
        asyncio.run(ZerodhaBrokerAdapter(FakeKite(fail=RuntimeError("broker down"))).place_order("NIFTY", "BUY", 2, 100))


def test_broker_adapter_rejected_order_and_status():
    from Backend.trading_system.broker import ZerodhaBrokerAdapter

    order = asyncio.run(ZerodhaBrokerAdapter(FakeKite(status="REJECTED")).get_order_status("kite-order-1"))
    assert order.status == "rejected"


def test_broker_adapter_token_expired():
    from Backend.trading_system.broker import ZerodhaBrokerAdapter

    with pytest.raises(PermissionError):
        asyncio.run(ZerodhaBrokerAdapter(FakeKite(fail=PermissionError("token expired"))).get_order_status("kite-order-1"))


def test_broker_adapter_cancel_order():
    from Backend.trading_system.broker import ZerodhaBrokerAdapter

    kite = FakeKite()
    asyncio.run(ZerodhaBrokerAdapter(kite).cancel_order("kite-order-1"))
    assert kite.cancelled is True


def test_positions_create_update_close_and_summary(monkeypatch):
    from Backend.application import position_store

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    monkeypatch.setattr(position_store, "_connect", lambda: connection)
    monkeypatch.setattr(position_store, "latest_candles", lambda symbol, interval, limit: [{"close": 110}])
    opened = position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 2, "entry_price": 100})
    assert opened["status"] == "open"
    open_positions = position_store.list_open_positions()
    assert open_positions[0]["open_pnl"] == 20
    closed = position_store.close_open_position(opened["id"], current_price=115)
    assert closed["status"] == "closed"
    summary = position_store.position_summary()
    assert summary["realized_pnl"] == 30
    assert summary["unrealized_pnl"] == 0
    connection.close()


def test_kill_switch_activate_blocks_and_deactivate_allows(monkeypatch):
    from Backend.application import kill_switch

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    monkeypatch.setattr(kill_switch, "_connect", lambda: connection)
    assert kill_switch.activate_kill_switch(reason="test", actor="admin")["active"] is True
    assert kill_switch.kill_switch_status()["active"] is True
    assert kill_switch.deactivate_kill_switch(actor="admin")["active"] is False
    connection.close()


def test_kill_switch_unauthorized_role_cannot_activate_deactivate(monkeypatch):
    with _app_client(monkeypatch) as app_client:
        admin = admin_headers(app_client)
        viewer = _role_headers(app_client, admin, "viewer-safety", "viewer")
        developer = _role_headers(app_client, admin, "developer-ks-denied", "developer")
        trader = _role_headers(app_client, admin, "trader-safety", "trader")

        assert app_client.post("/risk/kill-switch/activate", json={"reason": "test"}, headers=viewer).status_code == 403
        assert app_client.post("/risk/kill-switch/activate", json={"reason": "test"}, headers=developer).status_code == 403
        logs = app_client.get("/audit/logs", headers=admin).json()["events"]
        assert any(event["action"] == "Kill switch activation denied" for event in logs)
        assert app_client.post("/risk/kill-switch/deactivate", headers=trader).status_code == 403


def test_api_health_positions_risk_and_audit_access(monkeypatch):
    with _app_client(monkeypatch) as app_client:
        admin = admin_headers(app_client)
        ops = _role_headers(app_client, admin, "ops-safety", "ops")
        viewer = _role_headers(app_client, admin, "viewer-api-safety", "viewer")
        developer = _role_headers(app_client, admin, "developer-api-safety", "developer")

        assert app_client.get("/health").status_code == 200
        assert app_client.get("/positions/open").status_code == 401
        assert app_client.get("/positions/open", headers=viewer).status_code == 200
        assert app_client.get("/risk/kill-switch/status", headers=viewer).status_code == 200
        assert app_client.get("/audit/logs", headers=viewer).status_code == 403
        assert app_client.get("/audit/logs", headers=developer).status_code == 403
        assert app_client.get("/audit/logs", headers=ops).status_code == 200


def test_admin_trader_ops_can_activate_kill_switch(monkeypatch):
    with _app_client(monkeypatch) as app_client:
        admin = admin_headers(app_client)
        trader = _role_headers(app_client, admin, "trader-ks-safety", "trader")
        ops = _role_headers(app_client, admin, "ops-ks-safety", "ops")

        assert app_client.post("/risk/kill-switch/activate", json={"reason": "admin"}, headers=admin).status_code == 200
        assert app_client.post("/risk/kill-switch/deactivate", headers=admin).status_code == 200
        assert app_client.post("/risk/kill-switch/activate", json={"reason": "trader"}, headers=trader).status_code == 200
        assert app_client.post("/risk/kill-switch/deactivate", headers=admin).status_code == 200
        assert app_client.post("/risk/kill-switch/activate", json={"reason": "ops"}, headers=ops).status_code == 200
