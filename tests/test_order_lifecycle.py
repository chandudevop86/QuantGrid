from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def _actor(db):
    from Backend.domain.security.models import User

    actor = User(username="trader", password_hash="hash", role="trader")
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def _signal(**overrides):
    from Backend.domain.models.signal import StrategySignal

    values = {
        "strategy_name": "lifecycle",
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


def test_order_store_creates_and_transitions_order(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store

    created = order_store.create_order(
        {
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "broker_status": "created",
            "status": "requested",
        }
    )
    assert created["local_order_id"].startswith("ORD-")
    assert created["status"] == "requested"
    assert created["execution_mode"] == "live"
    assert created["broker_status"] == "created"

    updated, previous = order_store.transition_order(
        created["local_order_id"],
        "risk_approved",
        status_reason="ok",
        broker_status="risk_ok",
    )

    assert previous == "requested"
    assert updated["status"] == "risk_approved"
    assert updated["broker_status"] == "risk_ok"
    assert order_store.get_order(created["local_order_id"])["status"] == "risk_approved"
    assert len(order_store.list_orders()) == 1


def test_order_store_transitions_broker_submitted_and_rejected(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store

    created = order_store.create_order(
        {
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "status": "requested",
        }
    )

    submitted, previous = order_store.transition_order(
        created["local_order_id"],
        "broker_submitted",
        broker_order_id="BRK-1",
        broker_status="open",
        status_reason="broker accepted request",
    )
    rejected, previous_rejected = order_store.transition_order(
        created["local_order_id"],
        "rejected",
        broker_order_id="BRK-1",
        broker_status="rejected",
        status_reason="broker rejected order",
    )

    assert previous == "requested"
    assert submitted["status"] == "broker_submitted"
    assert submitted["broker_order_id"] == "BRK-1"
    assert previous_rejected == "broker_submitted"
    assert rejected["status"] == "rejected"
    assert rejected["broker_status"] == "rejected"


def test_order_store_finds_active_duplicate_order_key(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store

    created = order_store.create_order(
        {
            "strategy": "breakout",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": "broker_submitted",
        }
    )

    duplicate = order_store.get_active_order_by_key("NIFTY:BUY:BREAKOUT")

    assert created["order_key"] == "NIFTY:BUY:BREAKOUT"
    assert duplicate["local_order_id"] == created["local_order_id"]

    order_store.transition_order(created["local_order_id"], "filled")
    assert order_store.get_active_order_by_key("NIFTY:BUY:BREAKOUT") is None


def test_order_cancel_api_transitions_and_audits(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import AuditLog
    from Backend.presentation.api import orders_api

    init_database()
    created = order_store.create_order(
        {"symbol": "NIFTY", "side": "BUY", "quantity": 25, "entry_price": 100, "status": "requested"}
    )

    with SessionLocal() as db:
        result = asyncio.run(
            orders_api.cancel_order(
                created["local_order_id"],
                request=None,
                actor=_actor(db),
                _role="trader",
                execution_mode="paper",
                db=db,
            )
        )
        audit = db.query(AuditLog).filter(AuditLog.action == "order_status_transition").one()

    assert result["status"] == "cancelled"
    assert audit.target_id == created["local_order_id"]
    assert audit.status == "cancelled"


def test_order_read_apis_return_lifecycle_fields(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store
    from Backend.presentation.api import orders_api

    created = order_store.create_order(
        {
            "symbol": "NIFTY",
            "side": "SELL",
            "quantity": 50,
            "entry_price": 101,
            "execution_mode": "paper",
            "broker_status": "confirmed",
            "status": "filled",
        }
    )

    listed = orders_api.get_orders(_role="viewer")
    detail = orders_api.get_order_by_id(created["local_order_id"], _role="viewer")

    assert any(order["local_order_id"] == created["local_order_id"] for order in listed["orders"])
    assert detail["execution_mode"] == "paper"
    assert detail["broker_status"] == "confirmed"


def test_execution_does_not_create_position_when_broker_not_confirmed(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult
    from Backend.presentation.api import execution as execution_api
    from Backend.domain.engine.execution_engine import ExecutionEngine

    init_database()
    monkeypatch.setattr(execution_api, "_market_aligned", lambda signal: True)
    monkeypatch.setattr(
        execution_api,
        "validate_order_risk",
        lambda *args, **kwargs: SimpleNamespace(allowed=True, reason="OK", details={}, to_dict=lambda: {"allowed": True, "reason": "OK", "details": {}}),
    )
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: SimpleNamespace(valid_for_execution=True))
    monkeypatch.setattr(
        execution_api,
        "decide_signal",
        lambda *args, **kwargs: SimpleNamespace(score=20, regime="test", to_dict=lambda: {"score": 20}),
    )
    monkeypatch.setattr(execution_api, "evaluate_risk_gate", lambda *_args, **_kwargs: SimpleNamespace(allowed=True, reason="OK"))
    monkeypatch.setattr(
        execution_api,
        "validate_execution_constraints",
        lambda *_args, **_kwargs: SimpleNamespace(accepted=True, reason="OK", lot_size=1, quantity=1, required_margin=100),
    )
    monkeypatch.setattr(execution_api, "apply_order_constraints", lambda order, *_args, **_kwargs: order)
    monkeypatch.setattr(execution_api, "requested_quantity", lambda *_args, **_kwargs: 1)

    class UnconfirmedBroker:
        async def place_order(self, order):
            return BrokerOrderResult(
                broker_order_id="BRK-REJECT",
                status="open",
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                confirmed=True,
            )

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="rejected",
                symbol="NIFTY",
                side="BUY",
                quantity=1,
                confirmed=False,
            )

    with SessionLocal() as db:
        result = asyncio.run(
            execution_api._submit_paper_signal(
                _signal(),
                engine=ExecutionEngine(),
                execution_mode="paper",
                candles_1m=[{"timestamp": datetime.now(timezone.utc).isoformat(), "close": 100}],
                candles_15m=[{"timestamp": datetime.now(timezone.utc).isoformat(), "close": 100}],
                broker_client=UnconfirmedBroker(),
                db=db,
                request=None,
                actor=_actor(db),
            )
        )

    assert result["status"] == "rejected"
    assert position_store.position_summary()["open_positions"] == 0
    orders = order_store.list_orders()
    assert orders[0]["status"] == "rejected"
    assert orders[0]["broker_order_id"] == "BRK-REJECT"
    assert orders[0]["broker_status"] == "rejected"
    assert orders[0]["execution_mode"] == "paper"


def test_execution_creates_position_after_broker_confirmation_and_audits(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.engine.execution_engine import ExecutionEngine
    from Backend.domain.security.models import AuditLog
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult
    from Backend.presentation.api import execution as execution_api

    init_database()
    monkeypatch.setattr(execution_api, "_market_aligned", lambda signal: True)
    monkeypatch.setattr(
        execution_api,
        "validate_order_risk",
        lambda *args, **kwargs: SimpleNamespace(allowed=True, reason="OK", details={}, to_dict=lambda: {"allowed": True, "reason": "OK", "details": {}}),
    )
    monkeypatch.setattr(execution_api, "validate_live_candle", lambda *args, **kwargs: SimpleNamespace(valid_for_execution=True))
    monkeypatch.setattr(
        execution_api,
        "decide_signal",
        lambda *args, **kwargs: SimpleNamespace(score=20, regime="test", to_dict=lambda: {"score": 20}),
    )
    monkeypatch.setattr(execution_api, "evaluate_risk_gate", lambda *_args, **_kwargs: SimpleNamespace(allowed=True, reason="OK"))
    monkeypatch.setattr(
        execution_api,
        "validate_execution_constraints",
        lambda *_args, **_kwargs: SimpleNamespace(accepted=True, reason="OK", lot_size=1, quantity=1, required_margin=100),
    )
    monkeypatch.setattr(execution_api, "apply_order_constraints", lambda order, *_args, **_kwargs: order)
    monkeypatch.setattr(execution_api, "requested_quantity", lambda *_args, **_kwargs: 1)

    class ConfirmingBroker:
        async def place_order(self, order):
            return BrokerOrderResult(
                broker_order_id="BRK-FILLED",
                status="open",
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                confirmed=True,
            )

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol="NIFTY",
                side="BUY",
                quantity=1,
                price=101,
                confirmed=True,
            )

    with SessionLocal() as db:
        request = SimpleNamespace(headers={}, client=None, state=SimpleNamespace())
        result = asyncio.run(
            execution_api._submit_paper_signal(
                _signal(),
                engine=ExecutionEngine(),
                execution_mode="paper",
                candles_1m=[{"timestamp": datetime.now(timezone.utc).isoformat(), "close": 100}],
                candles_15m=[{"timestamp": datetime.now(timezone.utc).isoformat(), "close": 100}],
                broker_client=ConfirmingBroker(),
                db=db,
                request=request,
                actor=_actor(db),
            )
        )
        audited_statuses = {
            row.status
            for row in db.query(AuditLog)
            .filter(AuditLog.action == "order_status_transition")
            .all()
        }

    order = order_store.list_orders()[0]
    assert result["broker_confirmed"] is True
    assert order["status"] == "filled"
    assert order["broker_order_id"] == "BRK-FILLED"
    assert {"requested", "risk_approved", "broker_submitted", "filled"}.issubset(audited_statuses)
    assert position_store.position_summary()["open_positions"] == 1
