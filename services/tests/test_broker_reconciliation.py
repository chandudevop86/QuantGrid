from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def test_reconciliation_updates_rejected_order_and_missing_position(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, paper_trade_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    paper_trade_store.create_paper_trade(
        {
            "strategy": "breakout",
            "symbol": "NIFTY",
            "side": "BUY",
            "entry": 100,
            "stop_loss": 95,
            "target": 110,
            "status": "live_order_submitted",
            "broker_order_id": "REJECTED-1",
        }
    )
    paper_trade_store.create_paper_trade(
        {
            "strategy": "breakout",
            "symbol": "BANKNIFTY",
            "side": "BUY",
            "entry": 200,
            "stop_loss": 190,
            "target": 230,
            "status": "live_order_submitted",
            "broker_order_id": "FILLED-1",
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "BANKNIFTY", "transactionType": "BUY", "netQty": 10, "averagePrice": 201}]

        async def get_order_status(self, broker_order_id):
            if broker_order_id == "REJECTED-1":
                return BrokerOrderResult(
                    broker_order_id=broker_order_id,
                    status="rejected",
                    symbol="NIFTY",
                    side="BUY",
                    quantity=25,
                    price=100,
                    metadata={"raw_safe": {"orderStatus": "REJECTED"}},
                )
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol="BANKNIFTY",
                side="BUY",
                quantity=10,
                price=201,
                confirmed=True,
                metadata={"raw_safe": {"orderStatus": "TRADED"}},
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="paper"))

    assert summary["checked_orders"] == 2
    assert summary["mismatches"] == 2
    assert summary["fixed"] == 2
    rejected = [trade for trade in paper_trade_store.list_paper_trades() if trade["broker_order_id"] == "REJECTED-1"][0]
    assert rejected["status"] == "broker_rejected"
    assert rejected["broker_status"] == "rejected"
    assert rejected["raw_safe_broker_response"]["orderStatus"] == "REJECTED"
    created_position = position_store.find_position_by_broker_order_id("FILLED-1")
    assert created_position is not None
    assert created_position["quantity"] == 10


def test_reconciliation_marks_quantity_mismatch_for_review(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    position_store.create_open_position(
        {
            "broker_order_id": "OPEN-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 1,
            "entry_price": 100,
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 3, "averagePrice": 105}]

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="open",
                symbol="NIFTY",
                side="BUY",
                quantity=3,
                price=105,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="paper"))

    assert summary["mismatches"] == 1
    assert summary["fixed"] == 0
    assert summary["needs_review"] == 1
    position = position_store.find_position_by_broker_order_id("OPEN-1")
    assert position["quantity"] == 1
    assert position["entry_price"] == 100


def test_reconciliation_fixes_price_only_mismatch(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    position_store.create_open_position(
        {
            "broker_order_id": "PRICE-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 3,
            "entry_price": 100,
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 3, "averagePrice": 105}]

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="open",
                symbol="NIFTY",
                side="BUY",
                quantity=3,
                price=105,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="paper"))

    assert summary["mismatches"] == 1
    assert summary["fixed"] == 1
    assert summary["needs_review"] == 0
    position = position_store.find_position_by_broker_order_id("PRICE-1")
    assert position["quantity"] == 3
    assert position["entry_price"] == 105


def test_reconciliation_marks_broker_only_position_for_review(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import AuditLog, User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 3, "averagePrice": 105}]

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="not_found",
                symbol="",
                side="",
                quantity=0,
                confirmed=False,
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="paper"))
        audit = db.query(AuditLog).filter(AuditLog.action == "broker_reconciliation_change").first()

    assert summary["checked_orders"] == 0
    assert summary["checked_positions"] == 1
    assert summary["mismatches"] == 1
    assert summary["fixed"] == 0
    assert summary["needs_review"] == 1
    assert audit is not None
    assert "broker_position_local_missing" in audit.metadata_json


def test_reconciliation_closes_local_open_when_broker_closed(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import AuditLog, User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    opened = position_store.create_open_position(
        {
            "broker_order_id": "CLOSED-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 1,
            "entry_price": 100,
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="cancelled",
                symbol="NIFTY",
                side="BUY",
                quantity=1,
                price=99,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="paper"))
        audit = db.query(AuditLog).filter(AuditLog.action == "broker_reconciliation_change").first()

    closed = position_store.get_position(opened["id"])
    assert summary["mismatches"] == 1
    assert summary["fixed"] == 1
    assert summary["needs_review"] == 0
    assert closed["status"] == "closed"
    assert closed["exit_reason"] == "broker_cancelled"
    assert audit is not None
    assert "local_submitted_broker_rejected" in audit.metadata_json


def test_reconciliation_updates_lifecycle_order_when_broker_filled(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, order_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    local_order = order_store.create_order(
        {
            "local_order_id": "ORD-RECON-1",
            "broker_order_id": "BROKER-FILLED-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "status": "broker_submitted",
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 25, "averagePrice": 101}]

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                price=101,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="live"))

    updated_order = order_store.get_order(local_order["local_order_id"])
    created_position = position_store.find_position_by_broker_order_id("BROKER-FILLED-1")
    assert summary["mismatches"] == 2
    assert summary["fixed"] == 2
    assert summary["needs_review"] == 0
    assert updated_order["status"] == "filled"
    assert updated_order["broker_status"] == "filled"
    assert updated_order["entry_price"] == 101
    assert created_position is not None
    assert created_position["quantity"] == 25


def test_reconciliation_recovers_stale_pre_broker_order(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User

    init_database()
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    local_order = order_store.create_order(
        {
            "order_key": "NIFTY:BUY:BREAKOUT",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "status": "risk_approved",
            "created_at": stale_at,
            "updated_at": stale_at,
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            raise AssertionError("stale pre-broker order should not query broker without broker id")

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="live"))

    recovered = order_store.get_order(local_order["local_order_id"])
    assert summary["mismatches"] == 1
    assert summary["fixed"] == 1
    assert summary["needs_review"] == 0
    assert recovered["status"] == "failed"
    assert recovered["broker_status"] == "not_submitted"
    assert order_store.get_active_order_by_key("NIFTY:BUY:BREAKOUT") is None


def test_reconciliation_marks_ambiguous_submitted_order_without_broker_id_for_review(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User

    init_database()
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    local_order = order_store.create_order(
        {
            "order_key": "NIFTY:BUY:BREAKOUT",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "status": "broker_submitted",
            "created_at": stale_at,
            "updated_at": stale_at,
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            raise AssertionError("ambiguous local order without broker id should not query broker")

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor, execution_mode="live"))

    unchanged = order_store.get_order(local_order["local_order_id"])
    assert summary["mismatches"] == 1
    assert summary["fixed"] == 0
    assert summary["needs_review"] == 1
    assert unchanged["status"] == "broker_submitted"
    assert order_store.get_active_order_by_key("NIFTY:BUY:BREAKOUT")["local_order_id"] == local_order["local_order_id"]

def test_reconciliation_terminal_broker_state_releases_durable_submission_intent(monkeypatch):
    """Real reconciliation must terminalize durable intent and release its logical key."""
    configure_sqlalchemy_store(monkeypatch)

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from Backend.application import (
        broker_reconciliation,
        broker_submission_intent as intent,
        order_store,
    )
    from Backend.core.database import SessionLocal, engine, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()

    # broker_submission_intents is migration-managed rather than ORM-managed.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS broker_submission_intents ("
            "local_order_id VARCHAR(120) PRIMARY KEY, "
            "logical_key VARCHAR(160) NOT NULL, "
            "correlation_id VARCHAR(120) NOT NULL UNIQUE, "
            "broker_order_id VARCHAR(120) UNIQUE, "
            "status VARCHAR(40) NOT NULL, "
            "created_at VARCHAR(40) NOT NULL, "
            "updated_at VARCHAR(40) NOT NULL)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_intent_key "
            "ON broker_submission_intents(logical_key) "
            "WHERE status IN "
            "('claimed', 'reconciliation_required', 'submitted', 'open', 'partially_filled')"
        ))

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    local_order_id = "ORD-RECON-INTENT-1"
    broker_order_id = "BROKER-RECON-INTENT-1"
    logical_key = "NIFTY:BUY:RECONCILE-TERMINAL"

    local_order = order_store.create_order(
        {
            "local_order_id": local_order_id,
            "broker_order_id": broker_order_id,
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": "broker_submitted",
        }
    )

    intent.claim_submission(local_order_id, logical_key)
    intent.mark_submission_started(local_order_id)
    intent.record_broker_evidence(
        local_order_id,
        broker_order_id,
        "partially_filled",
    )

    # Active/partial durable intent must block duplicate submission.
    import pytest

    with pytest.raises(
        ValueError,
        match="DUPLICATE_OR_UNRESOLVED_BROKER_INTENT",
    ):
        intent.claim_submission(
            "ORD-RECON-DUPLICATE",
            logical_key,
        )

    class FakeBroker:
        async def get_positions(self):
            return [
                {
                    "tradingSymbol": "NIFTY",
                    "transactionType": "BUY",
                    "netQty": 25,
                    "averagePrice": 101,
                }
            ]

        async def get_order_status(self, requested_broker_order_id):
            assert requested_broker_order_id == broker_order_id
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                price=101,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(
            username="ops-pr65",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=FakeBroker(),
                actor=actor,
                execution_mode="paper",
            )
        )

    updated_order = order_store.get_order(local_order["local_order_id"])
    assert updated_order["status"] == "filled"
    assert updated_order["broker_status"] == "filled"

    with engine.connect() as conn:
        durable_status = conn.execute(
            text(
                "SELECT status FROM broker_submission_intents "
                "WHERE local_order_id = :local_order_id"
            ),
            {"local_order_id": local_order_id},
        ).scalar_one()

    assert durable_status == "filled"
    assert summary["needs_review"] == 0

    # Terminal authoritative evidence releases the logical key.
    replacement = intent.claim_submission(
        "ORD-RECON-REPLACEMENT",
        logical_key,
    )
    assert replacement["status"] == "claimed"



def test_reconciliation_not_found_does_not_release_durable_submission_intent(monkeypatch):
    """Missing broker lookup must remain fail-closed and keep the logical key blocked."""
    configure_sqlalchemy_store(monkeypatch)

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    import pytest

    from Backend.application import (
        broker_reconciliation,
        broker_submission_intent as intent,
        order_store,
    )
    from Backend.core.database import SessionLocal, engine, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS broker_submission_intents ("
            "local_order_id VARCHAR(120) PRIMARY KEY, "
            "logical_key VARCHAR(160) NOT NULL, "
            "correlation_id VARCHAR(120) NOT NULL UNIQUE, "
            "broker_order_id VARCHAR(120) UNIQUE, "
            "status VARCHAR(40) NOT NULL, "
            "created_at VARCHAR(40) NOT NULL, "
            "updated_at VARCHAR(40) NOT NULL)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_intent_key "
            "ON broker_submission_intents(logical_key) "
            "WHERE status IN "
            "('claimed', 'reconciliation_required', 'submitted', 'open', 'partially_filled')"
        ))

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    local_order_id = "ORD-RECON-MISSING-1"
    broker_order_id = "BROKER-RECON-MISSING-1"
    logical_key = "NIFTY:BUY:RECONCILE-MISSING"

    order_store.create_order(
        {
            "local_order_id": local_order_id,
            "broker_order_id": broker_order_id,
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": "broker_submitted",
        }
    )

    intent.claim_submission(local_order_id, logical_key)
    intent.mark_submission_started(local_order_id)
    intent.record_broker_evidence(
        local_order_id,
        broker_order_id,
        "submitted",
    )

    class MissingBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, requested_broker_order_id):
            assert requested_broker_order_id == broker_order_id
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="not_found",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                price=100,
                confirmed=False,
            )

    with SessionLocal() as db:
        actor = User(
            username="ops-pr65-missing",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=MissingBroker(),
                actor=actor,
                execution_mode="paper",
            )
        )

    with engine.connect() as conn:
        durable_status = conn.execute(
            text(
                "SELECT status FROM broker_submission_intents "
                "WHERE local_order_id = :local_order_id"
            ),
            {"local_order_id": local_order_id},
        ).scalar_one()

    # Missing lookup is ambiguous; durable submission evidence stays active.
    assert durable_status == "submitted"

    with pytest.raises(
        ValueError,
        match="DUPLICATE_OR_UNRESOLVED_BROKER_INTENT",
    ):
        intent.claim_submission(
            "ORD-RECON-MISSING-DUPLICATE",
            logical_key,
        )


def test_paper_reconciliation_ignores_live_orders(monkeypatch):
    """PAPER reconciliation must never inspect or mutate LIVE lifecycle orders."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User

    init_database()

    live_order = order_store.create_order(
        {
            "local_order_id": "ORD-LIVE-ISOLATION-1",
            "broker_order_id": "LIVE-BROKER-ISOLATION-1",
            "order_key": "NIFTY:BUY:LIVE-ISOLATION",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "status": "broker_submitted",
        }
    )

    queried = []

    class PaperBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            queried.append(broker_order_id)
            raise AssertionError(
                f"PAPER reconciliation queried LIVE order {broker_order_id}"
            )

    with SessionLocal() as db:
        actor = User(
            username="paper-isolation-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=PaperBroker(),
                actor=actor,
                execution_mode="paper",
            )
        )

    unchanged = order_store.get_order(live_order["local_order_id"])

    assert queried == []
    assert summary["checked_orders"] == 0
    assert unchanged["status"] == "broker_submitted"
    assert unchanged["execution_mode"] == "live"


def test_live_reconciliation_ignores_paper_orders(monkeypatch):
    """LIVE reconciliation must never inspect or mutate PAPER lifecycle orders."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User

    init_database()

    paper_order = order_store.create_order(
        {
            "local_order_id": "ORD-PAPER-ISOLATION-1",
            "broker_order_id": "PAPER-BROKER-ISOLATION-1",
            "order_key": "NIFTY:BUY:PAPER-ISOLATION",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": "broker_submitted",
        }
    )

    queried = []

    class LiveBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            queried.append(broker_order_id)
            raise AssertionError(
                f"LIVE reconciliation queried PAPER order {broker_order_id}"
            )

    with SessionLocal() as db:
        actor = User(
            username="live-isolation-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=LiveBroker(),
                actor=actor,
                execution_mode="live",
            )
        )

    unchanged = order_store.get_order(paper_order["local_order_id"])

    assert queried == []
    assert summary["checked_orders"] == 0
    assert unchanged["status"] == "broker_submitted"
    assert unchanged["execution_mode"] == "paper"


def test_paper_reconciliation_ignores_live_open_positions(monkeypatch):
    """PAPER reconciliation must not inspect or close LIVE positions."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User

    init_database()

    live_position = position_store.create_open_position(
        {
            "broker_order_id": "LIVE-POSITION-ISOLATION-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "current_price": 100,
            "execution_mode": "live",
        }
    )

    queried = []

    class PaperBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            queried.append(broker_order_id)
            raise AssertionError(
                f"PAPER reconciliation queried LIVE position order {broker_order_id}"
            )

    with SessionLocal() as db:
        actor = User(
            username="position-isolation-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=PaperBroker(),
                actor=actor,
                execution_mode="paper",
            )
        )

    unchanged = position_store.get_position(live_position["id"])

    assert queried == []
    assert summary["checked_positions"] == 0
    assert unchanged["status"] == "open"
    assert unchanged["execution_mode"] == "live"


def test_live_reconciliation_never_updates_paper_trade_store(monkeypatch):
    """LIVE reconciliation must never write through PAPER trade persistence."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()

    order_store.create_order(
        {
            "local_order_id": "ORD-LIVE-NO-PAPER-WRITE-1",
            "broker_order_id": "LIVE-NO-PAPER-WRITE-1",
            "order_key": "NIFTY:SELL:LIVE-NO-PAPER-WRITE",
            "symbol": "NIFTY",
            "side": "SELL",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "live",
            "status": "broker_submitted",
        }
    )

    paper_writes = []

    def forbidden_paper_write(*args, **kwargs):
        paper_writes.append((args, kwargs))
        raise AssertionError("LIVE reconciliation wrote to paper_trade_store")

    monkeypatch.setattr(
        broker_reconciliation,
        "update_paper_trade_status",
        forbidden_paper_write,
    )

    class LiveBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="rejected",
                symbol="NIFTY",
                side="SELL",
                quantity=25,
                price=100,
                confirmed=False,
            )

    with SessionLocal() as db:
        actor = User(
            username="live-no-paper-write-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=LiveBroker(),
                actor=actor,
                execution_mode="live",
            )
        )

    assert paper_writes == []
