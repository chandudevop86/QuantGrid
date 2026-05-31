from __future__ import annotations

import asyncio

import pytest

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def _actor(db):
    from Backend.domain.security.models import User

    actor = User(username="trader", password_hash="hash", role="trader")
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def test_manual_paper_exit_uses_latest_market_price_and_audits(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import AuditLog

    init_database()
    opened = position_store.create_open_position(
        {"symbol": "NIFTY", "side": "BUY", "quantity": 2, "entry_price": 100, "stop_loss": 95, "target": 110}
    )
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": 108}])

    with SessionLocal() as db:
        result = asyncio.run(
            trade_exit_engine.exit_position(
                opened["id"],
                db=db,
                actor=_actor(db),
                execution_mode="paper",
                reason="manual_exit",
            )
        )
        audit = db.query(AuditLog).filter(AuditLog.action == "position_exit").one()

    closed = result["position"]
    assert closed["status"] == "closed"
    assert closed["exit_price"] == 108
    assert closed["exit_reason"] == "manual_exit"
    assert closed["closed_pnl"] == 16
    assert audit.status == "closed"


@pytest.mark.parametrize(
    ("side", "price", "reason"),
    [
        ("BUY", 94, "stop_loss"),
        ("BUY", 111, "target"),
        ("SELL", 106, "stop_loss"),
        ("SELL", 89, "target"),
    ],
)
def test_exit_rule_detects_stop_and_target(side, price, reason):
    from Backend.application.trade_exit_engine import evaluate_exit_rule

    position = {
        "symbol": "NIFTY",
        "side": side,
        "quantity": 1,
        "entry_price": 100,
        "stop_loss": 95 if side == "BUY" else 105,
        "target": 110 if side == "BUY" else 90,
        "current_price": price,
    }

    decision = evaluate_exit_rule(position)

    assert decision.should_exit is True
    assert decision.reason == reason


def test_exit_all_closes_open_positions(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database

    init_database()
    position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 1, "entry_price": 100})
    position_store.create_open_position({"symbol": "BANKNIFTY", "side": "SELL", "quantity": 1, "entry_price": 200})
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": 105}])

    with SessionLocal() as db:
        result = asyncio.run(
            trade_exit_engine.exit_all_positions(
                db=db,
                actor=_actor(db),
                execution_mode="paper",
                reason="manual_exit",
            )
        )

    assert result["checked"] == 2
    assert result["exited"] == 2
    assert position_store.position_summary()["open_positions"] == 0


def test_live_exit_requires_broker_confirmation(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    opened = position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 2, "entry_price": 100})
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": 104}])

    class ConfirmingBroker:
        async def place_order(self, order):
            assert order.side == "SELL"
            assert order.quantity == 2
            return BrokerOrderResult(
                broker_order_id="EXIT-1",
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
                side="SELL",
                quantity=2,
                price=104,
                confirmed=True,
                metadata={"raw_safe": {"orderStatus": "TRADED"}},
            )

    with SessionLocal() as db:
        result = asyncio.run(
            trade_exit_engine.exit_position(
                opened["id"],
                db=db,
                actor=_actor(db),
                execution_mode="live",
                broker_client=ConfirmingBroker(),
            )
        )

    assert result["position"]["status"] == "closed"
    assert result["position"]["exit_price"] == 104
    assert result["broker"]["broker_order_id"] == "EXIT-1"


def test_live_exit_does_not_close_when_broker_rejects(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    opened = position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 2, "entry_price": 100})
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": 104}])

    class RejectingBroker:
        async def place_order(self, order):
            return BrokerOrderResult(
                broker_order_id="EXIT-REJECTED",
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
                side="SELL",
                quantity=2,
                confirmed=False,
            )

    with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="broker exit not confirmed"):
            asyncio.run(
                trade_exit_engine.exit_position(
                    opened["id"],
                    db=db,
                    actor=_actor(db),
                    execution_mode="live",
                    broker_client=RejectingBroker(),
                )
            )

    assert position_store.get_position(opened["id"])["status"] == "open"
