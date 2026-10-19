from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_exit_rule_detects_trailing_stop_loss():
    from Backend.application.trade_exit_engine import evaluate_exit_rule

    position = {
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 1,
        "entry_price": 100,
        "stop_loss": 95,
        "target": 120,
        "trailing_stop_loss": 106,
        "current_price": 105,
    }

    decision = evaluate_exit_rule(position)

    assert decision.should_exit is True
    assert decision.reason == "trailing_stop_loss"
    assert decision.details == {"trailing_stop_loss": 106.0}


def test_exit_rule_detects_market_close(monkeypatch):
    from Backend.application import trade_exit_engine

    monkeypatch.setenv("QUANTGRID_MARKET_CLOSE_EXIT", "true")
    monkeypatch.setattr(
        trade_exit_engine,
        "get_market_session",
        lambda now=None: SimpleNamespace(market_live=False, status="closed"),
    )

    decision = trade_exit_engine.evaluate_exit_rule(
        {
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 1,
            "entry_price": 100,
            "current_price": 101,
        }
    )

    assert decision.should_exit is True
    assert decision.reason == "market_close"
    assert decision.details == {"market_status": "closed"}


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


def test_monitor_open_positions_exits_when_rule_triggers(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database

    init_database()
    position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 1, "entry_price": 100, "target": 105})
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": 106}])
    monkeypatch.setattr(position_store, "latest_candles", lambda *_args, **_kwargs: [{"close": 106}])

    with SessionLocal() as db:
        result = asyncio.run(
            trade_exit_engine.monitor_open_positions(
                db=db,
                actor=_actor(db),
                execution_mode="paper",
            )
        )

    assert result["checked"] == 1
    assert result["exited"] == 1
    assert result["positions"][0]["exit_reason"] == "target"


@pytest.mark.parametrize(
    ("price", "reason", "expected_pnl"),
    [
        (94, "stop_loss", -6),
        (111, "target", 11),
    ],
)
def test_monitor_open_positions_closes_on_stop_loss_and_target(monkeypatch, price, reason, expected_pnl):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database

    init_database()
    opened = position_store.create_open_position(
        {
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 1,
            "entry_price": 100,
            "stop_loss": 95,
            "target": 110,
        }
    )
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": price}])
    monkeypatch.setattr(position_store, "latest_candles", lambda *_args, **_kwargs: [{"close": price}])

    with SessionLocal() as db:
        result = asyncio.run(
            trade_exit_engine.monitor_open_positions(
                db=db,
                actor=_actor(db),
                execution_mode="paper",
            )
        )

    closed = position_store.get_position(opened["id"])
    assert result["exited"] == 1
    assert closed["status"] == "closed"
    assert closed["exit_reason"] == reason
    assert closed["closed_pnl"] == expected_pnl


def test_position_exit_apis(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.presentation.api import positions_api

    init_database()
    first = position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 1, "entry_price": 100})
    second = position_store.create_open_position({"symbol": "BANKNIFTY", "side": "SELL", "quantity": 1, "entry_price": 200})

    rules = positions_api.get_exit_rules(_role="viewer")
    assert rules["rules"]["manual_exit"] is True
    assert len(rules["open_positions"]) == 2

    with SessionLocal() as db:
        actor = _actor(db)
        single = asyncio.run(
            positions_api.exit_single_position(
                first["id"],
                request=None,
                payload=positions_api.ExitRequest(reason="manual_exit", exit_price=103),
                actor=actor,
                _role="trader",
                execution_mode="paper",
                db=db,
            )
        )
        all_result = asyncio.run(
            positions_api.exit_all_open_positions(
                request=None,
                payload=positions_api.ExitRequest(reason="manual_exit", exit_price=198),
                actor=actor,
                _role="trader",
                execution_mode="paper",
                db=db,
            )
        )

    assert single["position"]["id"] == first["id"]
    assert single["position"]["status"] == "closed"
    assert all_result["checked"] == 1
    assert all_result["positions"][0]["position"]["id"] == second["id"]


def test_live_exit_requires_broker_confirmation(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    opened = position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 2, "entry_price": 100, "execution_mode": "live"})
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
                filled_quantity=2,
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
    opened = position_store.create_open_position({"symbol": "NIFTY", "side": "BUY", "quantity": 2, "entry_price": 100, "execution_mode": "live"})
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


def test_claim_exit_intent_is_atomic_and_persistent(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application.position_store import claim_exit_intent, create_open_position, get_position
    from Backend.core.database import init_database

    init_database()
    position = create_open_position({
        "symbol": "NIFTY", "side": "BUY", "quantity": 2,
        "entry_price": 100, "execution_mode": "live",
    })
    assert claim_exit_intent(position["id"], "EXIT-TEST") is True
    assert claim_exit_intent(position["id"], "EXIT-SECOND") is False
    stored = get_position(position["id"])
    assert stored["pending_exit_correlation_id"] == "EXIT-TEST"
    assert stored["pending_exit_broker_order_id"] is None


def test_live_exit_timeout_never_resubmits(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database

    init_database()
    opened = position_store.create_open_position({
        "symbol": "NIFTY", "side": "BUY", "quantity": 2,
        "entry_price": 100, "execution_mode": "live",
    })

    class AcceptedThenTimeout:
        calls = 0

        async def place_order(self, order):
            self.calls += 1
            saved = position_store.get_position(opened["id"])
            assert saved["pending_exit_correlation_id"] == order.metadata["correlation_id"]
            assert saved["pending_exit_broker_order_id"] is None
            raise TimeoutError("simulated broker acceptance with lost response")

    broker = AcceptedThenTimeout()
    with SessionLocal() as db:
        actor = _actor(db)
        with pytest.raises(TimeoutError):
            asyncio.run(trade_exit_engine.exit_position(
                opened["id"], db=db, actor=actor, execution_mode="live",
                exit_price=104, broker_client=broker,
            ))
        with pytest.raises(RuntimeError, match="EXIT_BROKER_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED"):
            asyncio.run(trade_exit_engine.exit_position(
                opened["id"], db=db, actor=actor, execution_mode="live",
                exit_price=104, broker_client=broker,
            ))

    assert broker.calls == 1
    assert position_store.get_position(opened["id"])["status"] == "open"


def test_live_exit_unconfirmed_fill_does_not_close_or_resend(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    opened = position_store.create_open_position({
        "symbol": "NIFTY", "side": "BUY", "quantity": 2,
        "entry_price": 100, "execution_mode": "live",
    })

    class UnconfirmedBroker:
        calls = 0

        async def place_order(self, order):
            self.calls += 1
            return BrokerOrderResult(
                broker_order_id="EXIT-SUBMITTED", status="open",
                symbol="NIFTY", side="SELL", quantity=2,
                confirmed=False,
            )

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id, status="filled",
                symbol="NIFTY", side="SELL", quantity=2,
                price=104, confirmed=False,
            )

    broker = UnconfirmedBroker()
    with SessionLocal() as db:
        actor = _actor(db)
        for _ in range(2):
            with pytest.raises(RuntimeError, match="broker exit not confirmed"):
                asyncio.run(trade_exit_engine.exit_position(
                    opened["id"], db=db, actor=actor, execution_mode="live",
                    exit_price=104, broker_client=broker,
                ))
    assert broker.calls == 1
    saved = position_store.get_position(opened["id"])
    assert saved["pending_exit_broker_order_id"] == "EXIT-SUBMITTED"
    assert saved["status"] == "open"


def test_paper_monitor_never_exits_live_position(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database

    init_database()
    paper = position_store.create_open_position({
        "symbol": "NIFTY", "side": "BUY", "quantity": 1,
        "entry_price": 100, "target": 105, "execution_mode": "paper",
    })
    live = position_store.create_open_position({
        "symbol": "NIFTY", "side": "BUY", "quantity": 1,
        "entry_price": 100, "target": 105, "execution_mode": "live",
    })
    monkeypatch.setattr(trade_exit_engine, "latest_candles", lambda *_args, **_kwargs: [{"close": 106}])
    monkeypatch.setattr(position_store, "latest_candles", lambda *_args, **_kwargs: [{"close": 106}])
    with SessionLocal() as db:
        result = asyncio.run(trade_exit_engine.monitor_open_positions(
            db=db, actor=_actor(db), execution_mode="paper",
        ))
    assert result["checked"] == 1
    assert position_store.get_position(paper["id"])["status"] == "closed"
    assert position_store.get_position(live["id"])["status"] == "open"


def test_live_exit_rejects_partial_or_wrong_instrument_fill(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import position_store, trade_exit_engine
    from Backend.core.database import SessionLocal, init_database
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    opened = position_store.create_open_position({
        "symbol": "NIFTY", "side": "BUY", "quantity": 2,
        "entry_price": 100, "execution_mode": "live",
    })

    class MismatchedBroker:
        calls = 0

        async def place_order(self, order):
            self.calls += 1
            return BrokerOrderResult(
                broker_order_id="EXIT-PARTIAL", status="open", symbol="NIFTY",
                side="SELL", quantity=2, confirmed=False,
            )

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id, status="filled", symbol="BANKNIFTY",
                side="SELL", quantity=2, filled_quantity=1, price=104,
                confirmed=True,
            )

    broker = MismatchedBroker()
    with SessionLocal() as db:
        actor = _actor(db)
        for _ in range(2):
            with pytest.raises(RuntimeError, match="EXIT_FILL_MISMATCH_RECONCILIATION_REQUIRED"):
                asyncio.run(trade_exit_engine.exit_position(
                    opened["id"], db=db, actor=actor, execution_mode="live",
                    exit_price=104, broker_client=broker,
                ))
    assert broker.calls == 1
    assert position_store.get_position(opened["id"])["status"] == "open"
