from __future__ import annotations

import asyncio
from datetime import datetime
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
        "signal_time": datetime.utcnow(),
        "metadata": {"quantity": 1, "score": 20, "validation_passed": True},
    }
    values.update(overrides)
    return StrategySignal(**values)


def test_order_store_creates_and_transitions_order(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import order_store

    created = order_store.create_order(
        {"symbol": "NIFTY", "side": "BUY", "quantity": 25, "entry_price": 100, "status": "requested"}
    )
    assert created["local_order_id"].startswith("ORD-")
    assert created["status"] == "requested"

    updated, previous = order_store.transition_order(
        created["local_order_id"],
        "risk_approved",
        status_reason="ok",
    )

    assert previous == "requested"
    assert updated["status"] == "risk_approved"
    assert order_store.get_order(created["local_order_id"])["status"] == "risk_approved"
    assert len(order_store.list_orders()) == 1


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
                candles_1m=[{"timestamp": datetime.utcnow().isoformat(), "close": 100}],
                candles_15m=[{"timestamp": datetime.utcnow().isoformat(), "close": 100}],
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
