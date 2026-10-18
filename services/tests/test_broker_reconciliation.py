from __future__ import annotations

import pytest

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
                    confirmed=True,
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
    reconciled_order = order_store.get_order(local_order_id)
    assert reconciled_order["status"] == "reconciliation_required"

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



def test_paper_restart_not_found_keeps_open_position_and_requires_review(monkeypatch):
    """Fresh PAPER broker after restart must not reject orders or close positions."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import PaperBrokerClient

    init_database()

    broker_order_id = "PAPER-BEFORE-RESTART-1"
    local_order = order_store.create_order(
        {
            "local_order_id": "ORD-BEFORE-RESTART-1",
            "broker_order_id": broker_order_id,
            "order_key": "NIFTY:BUY:RESTART-SAFETY",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": "broker_submitted",
        }
    )
    position = position_store.create_open_position(
        {
            "broker_order_id": broker_order_id,
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "current_price": 100,
            "execution_mode": "paper",
        }
    )

    # Simulate a worker/server restart: a new PaperBrokerClient has an empty
    # process-local order cache and therefore returns not_found for the
    # previously persisted broker order id.
    restarted_broker = PaperBrokerClient()
    assert restarted_broker.orders == {}

    with SessionLocal() as db:
        actor = User(
            username="paper-restart-safety",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=restarted_broker,
                actor=actor,
                execution_mode="paper",
            )
        )

    updated_order = order_store.get_order(local_order["local_order_id"])
    updated_position = position_store.get_position(position["id"])

    assert summary["fixed"] == 0
    assert summary["needs_review"] >= 1
    assert summary["errors"] == []
    assert updated_order["status"] == "reconciliation_required"
    assert updated_position["status"] == "open"


def test_paper_not_found_never_closes_position_without_local_order(monkeypatch):
    """Position-only PAPER state must also survive ambiguous not_found."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import PaperBrokerClient

    init_database()

    position = position_store.create_open_position(
        {
            "broker_order_id": "PAPER-POSITION-ONLY-RESTART",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 25,
            "entry_price": 100,
            "current_price": 100,
            "execution_mode": "paper",
        }
    )

    with SessionLocal() as db:
        actor = User(
            username="paper-position-restart-safety",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=PaperBrokerClient(),
                actor=actor,
                execution_mode="paper",
            )
        )

    updated_position = position_store.get_position(position["id"])
    assert summary["fixed"] == 0
    assert summary["needs_review"] >= 1
    assert updated_position["status"] == "open"



@pytest.mark.parametrize(
    "protection_scenario",
    ["valid", "wrong_parent", "unconfirmed"],
)
def test_live_partial_fill_persists_filled_position_and_keeps_order_active(
    monkeypatch, protection_scenario
):
    configure_sqlalchemy_store(monkeypatch)

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from Backend.application import broker_reconciliation, broker_submission_intent as intent, order_store, position_store
    from Backend.core.database import SessionLocal, engine, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS broker_submission_intents ("
            "local_order_id VARCHAR(120) PRIMARY KEY, logical_key VARCHAR(160) NOT NULL, "
            "correlation_id VARCHAR(120) NOT NULL UNIQUE, broker_order_id VARCHAR(120) UNIQUE, "
            "status VARCHAR(40) NOT NULL, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)"
        ))
    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    local_id = "ORD-LIVE-PARTIAL-1"
    broker_id = "DHAN-PARTIAL-1"
    order_store.create_order({
        "local_order_id": local_id, "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:PARTIAL", "symbol": "NIFTY", "side": "BUY",
        "quantity": 25, "entry_price": 100, "execution_mode": "live",
        "status": "broker_submitted",
    })
    intent.claim_submission(local_id, "NIFTY:BUY:PARTIAL")
    intent.mark_submission_started(local_id)
    intent.record_broker_evidence(local_id, broker_id, "submitted")

    class PartialBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 10, "averagePrice": 101}]
        async def get_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="partially_filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=10, remaining_quantity=15,
                price=101, confirmed=True,
            )
        async def get_super_order_status(self, requested):
            assert requested == broker_id
            return BrokerOrderResult(
                broker_order_id=(
                    "WRONG-SUPER-ORDER"
                    if protection_scenario == "wrong_parent"
                    else broker_id
                ),
                status="partially_filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=10, remaining_quantity=15,
                price=101, confirmed=protection_scenario != "unconfirmed",
                metadata={"super_order": {
                    "legs": {"STOP_LOSS_LEG": {"quantity": 10, "remaining_quantity": 10, "status": "open"}},
                    "protection": {
                        "exposed_quantity": 10, "stop_loss_present": True,
                        "stop_loss_active": True, "protected": True,
                    },
                }},
            )

    with SessionLocal() as db:
        actor = User(username="partial-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=PartialBroker(), actor=actor, execution_mode="live"
        ))

    updated = order_store.get_order(local_id)
    positions = position_store.list_open_positions(execution_mode="live")
    if protection_scenario == "valid":
        assert updated["status"] == "partially_filled"
        assert len(positions) == 1
        assert positions[0]["quantity"] == 10
    else:
        assert updated["status"] == "reconciliation_required"
        assert not positions
    with engine.connect() as conn:
        durable = conn.execute(text(
            "SELECT status FROM broker_submission_intents WHERE local_order_id=:id"
        ), {"id": local_id}).scalar_one()
    assert durable == (
        "partially_filled" if protection_scenario == "valid" else "submitted"
    )



@pytest.mark.parametrize("missing_lookup", [False, True])
def test_live_filled_exposure_without_super_order_stop_requires_review(monkeypatch, missing_lookup):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    from Backend.application.notification_entity import NotificationEntity

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    init_database()
    broker_id = "DHAN-LIVE-NO-STOP-1"
    local_id = "ORD-LIVE-NO-STOP-1"
    order_store.create_order({
        "local_order_id": local_id, "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:NO-STOP", "symbol": "NIFTY", "side": "BUY",
        "quantity": 25, "entry_price": 100, "execution_mode": "live",
        "status": "broker_submitted",
    })

    class UnprotectedBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 25, "averagePrice": 100}]
        async def get_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=25, remaining_quantity=0,
                price=100, confirmed=True,
            )
        async def get_super_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=25, remaining_quantity=0,
                price=100, confirmed=True,
                metadata={"super_order": {"protection": {
                    "exposed_quantity": 25, "stop_loss_present": False,
                    "stop_loss_active": False, "protected": False,
                }}},
            )

    # A broker lacking the Super Order lookup must also fail closed.
    # Removing the method exercises the missing-adapter recovery path.
    if missing_lookup:
        monkeypatch.delattr(UnprotectedBroker, "get_super_order_status")

    with SessionLocal() as db:
        actor = User(username="live-protection-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=UnprotectedBroker(), actor=actor, execution_mode="live"
        ))

    updated = order_store.get_order(local_id)
    assert summary["needs_review"] >= 1
    assert updated["status"] == "reconciliation_required"
    with SessionLocal() as db:
        records = db.query(NotificationEntity).filter(
            NotificationEntity.channel == "telegram",
            NotificationEntity.subject.like(
                "%LIVE position protection failure%"
            ),
        ).all()

    assert len(records) == 1
    notification = records[0]
    assert notification.status == "PENDING"
    assert notification.recipient == "test-chat"
    assert "CRITICAL" in notification.subject.upper()
    assert broker_id in notification.message
    assert "stop" in notification.message.lower()


@pytest.mark.parametrize("missing_lookup", [False, True])
def test_live_protection_alert_failure_does_not_interrupt_reconciliation(monkeypatch, missing_lookup):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    persistence_attempts = []

    def fake_enqueue_notifications_atomic(db, **kwargs):
        persistence_attempts.append(kwargs)
        raise RuntimeError("Simulated notification database outage")

    monkeypatch.setattr(
        broker_reconciliation,
        "enqueue_notifications_atomic",
        fake_enqueue_notifications_atomic,
        raising=False,
    )

    init_database()
    broker_id = "DHAN-LIVE-NO-STOP-1"
    local_id = "ORD-LIVE-NO-STOP-1"
    order_store.create_order({
        "local_order_id": local_id, "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:NO-STOP", "symbol": "NIFTY", "side": "BUY",
        "quantity": 25, "entry_price": 100, "execution_mode": "live",
        "status": "broker_submitted",
    })

    class UnprotectedBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 25, "averagePrice": 100}]
        async def get_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=25, remaining_quantity=0,
                price=100, confirmed=True,
            )
        async def get_super_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=25, remaining_quantity=0,
                price=100, confirmed=True,
                metadata={"super_order": {"protection": {
                    "exposed_quantity": 25, "stop_loss_present": False,
                    "stop_loss_active": False, "protected": False,
                }}},
            )

    # A broker lacking the Super Order lookup must also fail closed.
    # Removing the method exercises the missing-adapter recovery path.
    if missing_lookup:
        monkeypatch.delattr(UnprotectedBroker, "get_super_order_status")

    with SessionLocal() as db:
        actor = User(username="live-protection-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=UnprotectedBroker(), actor=actor, execution_mode="live"
        ))

    updated = order_store.get_order(local_id)
    assert summary["needs_review"] >= 1
    assert updated["status"] == "reconciliation_required"
    assert any(
        broker_id in error
        and "critical LIVE protection alert persistence failed" in error
        for error in summary["errors"]
    )
    assert all(
        "Simulated notification database outage" not in error
        for error in summary["errors"]
    )
    assert len(persistence_attempts) == 1
    attempted = persistence_attempts[0]
    assert ("telegram", "test-chat") in attempted["destinations"]
    assert isinstance(attempted["incident_key"], str)
    assert attempted["incident_key"]
    assert "CRITICAL" in attempted["subject"].upper()
    assert broker_id in attempted["message"]
    assert "stop" in attempted["message"].lower()


def test_live_undercovered_super_order_stop_requires_review(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    broker_id = "DHAN-LIVE-UNDERCOVERED-1"
    local_id = "ORD-LIVE-UNDERCOVERED-1"
    order_store.create_order({
        "local_order_id": local_id, "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:UNDERCOVERED", "symbol": "NIFTY", "side": "BUY",
        "quantity": 25, "entry_price": 100, "execution_mode": "live",
        "status": "broker_submitted",
    })

    class UndercoveredBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 10, "averagePrice": 100}]
        async def get_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="partially_filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=10, remaining_quantity=15,
                price=100, confirmed=True,
            )
        async def get_super_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="partially_filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=10, remaining_quantity=15,
                price=100, confirmed=True,
                metadata={"super_order": {"protection": {
                    "exposed_quantity": 10, "stop_loss_present": True,
                    "stop_loss_active": False, "protected": False,
                }}},
            )

    with SessionLocal() as db:
        actor = User(username="live-undercovered-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=UndercoveredBroker(), actor=actor, execution_mode="live"
        ))

    updated = order_store.get_order(local_id)
    assert summary["needs_review"] >= 1
    assert updated["status"] == "reconciliation_required"


@pytest.mark.parametrize("stale_protected_flag", [False, True])
def test_live_restart_position_requires_protection_even_with_zero_reported_fill(
    monkeypatch, stale_protected_flag
):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    broker_id = "DHAN-RESTART-STALE-FILL-1"
    local_id = "ORD-RESTART-STALE-FILL-1"
    order_store.create_order({
        "local_order_id": local_id, "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:RESTART-STALE-FILL", "symbol": "NIFTY",
        "side": "BUY", "quantity": 10, "entry_price": 100,
        "execution_mode": "live", "status": "broker_submitted",
    })
    position_store.create_open_position({
        "broker_order_id": broker_id, "symbol": "NIFTY", "side": "BUY",
        "quantity": 10, "entry_price": 100, "execution_mode": "live",
    })

    class StaleFillBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY",
                     "netQty": 10, "averagePrice": 100}]

        async def get_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="open", symbol="NIFTY",
                side="BUY", quantity=10, filled_quantity=0,
                remaining_quantity=10, price=100, confirmed=True,
            )

    if stale_protected_flag:
        async def stale_super_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status="open", symbol="NIFTY",
                side="BUY", quantity=10, filled_quantity=0,
                remaining_quantity=10, price=100, confirmed=True,
                metadata={"super_order": {
                    "legs": {"STOP_LOSS_LEG": {"quantity": 0, "status": "open"}},
                    "protection": {
                        "protected": True, "stop_loss_present": True,
                        "stop_loss_active": True, "exposed_quantity": 0,
                    },
                }},
            )
        StaleFillBroker.get_super_order_status = stale_super_order_status

    with SessionLocal() as db:
        actor = User(username="restart-protection-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=StaleFillBroker(), actor=actor,
            execution_mode="live",
        ))

    assert summary["needs_review"] >= 1
    assert order_store.get_order(local_id)["status"] == "reconciliation_required"
    assert position_store.find_position_by_broker_order_id(
        broker_id, execution_mode="live"
    )["status"] == "open"


@pytest.mark.parametrize("terminal_status", ["rejected", "cancelled"])
def test_live_terminal_entry_does_not_close_persisted_exposure(monkeypatch, terminal_status):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    broker_id = "DHAN-LIVE-TERMINAL-ENTRY-1"
    local_id = "ORD-LIVE-TERMINAL-ENTRY-1"
    order_store.create_order({
        "local_order_id": local_id, "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:TERMINAL-ENTRY", "symbol": "NIFTY",
        "side": "BUY", "quantity": 10, "entry_price": 100,
        "execution_mode": "live", "status": "broker_submitted",
    })
    position_store.create_open_position({
        "broker_order_id": broker_id, "symbol": "NIFTY", "side": "BUY",
        "quantity": 10, "entry_price": 100, "execution_mode": "live",
    })

    class TerminalEntryBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY",
                     "netQty": 10, "averagePrice": 100}]

        async def get_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status=terminal_status,
                symbol="NIFTY", side="BUY", quantity=10,
                filled_quantity=0, remaining_quantity=10,
                price=100, confirmed=True,
            )

        async def get_super_order_status(self, requested):
            return BrokerOrderResult(
                broker_order_id=broker_id, status=terminal_status,
                symbol="NIFTY", side="BUY", quantity=10,
                filled_quantity=0, remaining_quantity=10,
                price=100, confirmed=True,
                metadata={"super_order": {
                    "legs": {"STOP_LOSS_LEG": {"quantity": 10, "status": "open"}},
                    "protection": {
                        "protected": True, "stop_loss_present": True,
                        "stop_loss_active": True, "exposed_quantity": 0,
                    },
                }},
            )

    with SessionLocal() as db:
        actor = User(username="terminal-entry-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=TerminalEntryBroker(), actor=actor,
            execution_mode="live",
        ))

    assert summary["needs_review"] >= 1
    assert order_store.get_order(local_id)["status"] == "reconciliation_required"
    assert position_store.find_position_by_broker_order_id(
        broker_id, execution_mode="live"
    )["status"] == "open"


@pytest.fixture(autouse=True)
def isolate_reconciliation_status_file(tmp_path, monkeypatch):
    """Isolate reconciliation status even when backend modules reload."""
    original_configure = configure_sqlalchemy_store

    def configure_and_isolate(patch):
        original_configure(patch)

        from Backend.application import broker_reconciliation

        patch.setattr(
            broker_reconciliation,
            "STATUS_FILE",
            tmp_path / "broker_reconciliation_status.json",
        )

    monkeypatch.setitem(
        globals(),
        "configure_sqlalchemy_store",
        configure_and_isolate,
    )


def test_live_remaining_stop_quantity_undercovered_requires_review(monkeypatch):
    """An active stop with insufficient remaining quantity is not protective."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()

    broker_id = "DHAN-LIVE-REMAINING-STOP-1"
    local_id = "ORD-LIVE-REMAINING-STOP-1"

    order_store.create_order({
        "local_order_id": local_id,
        "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:REMAINING-STOP",
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 25,
        "entry_price": 100,
        "execution_mode": "live",
        "status": "broker_submitted",
    })

    class UndercoveredRemainingStopBroker:
        async def get_positions(self):
            return [{
                "tradingSymbol": "NIFTY",
                "transactionType": "BUY",
                "netQty": 10,
                "averagePrice": 100,
            }]

        async def get_order_status(self, requested):
            assert requested == broker_id
            return BrokerOrderResult(
                broker_order_id=broker_id,
                status="partially_filled",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                filled_quantity=10,
                remaining_quantity=15,
                price=100,
                confirmed=True,
            )

        async def get_super_order_status(self, requested):
            assert requested == broker_id
            return BrokerOrderResult(
                broker_order_id=broker_id,
                status="partially_filled",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                filled_quantity=10,
                remaining_quantity=15,
                price=100,
                confirmed=True,
                metadata={
                    "super_order": {
                        "legs": {
                            "STOP_LOSS_LEG": {
                                "status": "partially_filled",
                                "quantity": 25,
                                "remaining_quantity": 5,
                                "triggered_quantity": 25,
                            }
                        },
                        "protection": {
                            "exposed_quantity": 10,
                            "stop_loss_present": True,
                            "stop_loss_active": True,
                            "protected": True,
                        },
                    }
                },
            )

    with SessionLocal() as db:
        actor = User(
            username="remaining-stop-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        summary = asyncio.run(
            broker_reconciliation.reconcile_broker_state(
                db=db,
                broker_client=UndercoveredRemainingStopBroker(),
                actor=actor,
                execution_mode="live",
            )
        )

    assert summary["needs_review"] >= 1
    assert order_store.get_order(local_id)["status"] == "reconciliation_required"


def test_reconciliation_intent_rejection_distinguishes_legacy_and_conflict(
    tmp_path, monkeypatch
):
    """Missing legacy intents differ from conflicting existing intents."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from Backend.application import broker_reconciliation as reconciliation
    from Backend.application import broker_submission_intent as intent

    engine = create_engine(
        "sqlite:///" + str(tmp_path / "reconciliation-intents.db")
    )

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE broker_submission_intents ("
            "local_order_id VARCHAR(120) PRIMARY KEY, "
            "logical_key VARCHAR(160) NOT NULL, "
            "correlation_id VARCHAR(120) NOT NULL UNIQUE, "
            "broker_order_id VARCHAR(120) UNIQUE, "
            "status VARCHAR(40) NOT NULL, "
            "created_at VARCHAR(40) NOT NULL, "
            "updated_at VARCHAR(40) NOT NULL)"
        ))

    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(intent, "SessionLocal", sessions)
    monkeypatch.setattr(reconciliation, "SessionLocal", sessions)

    # Legacy order: no durable intent record.
    assert reconciliation._submission_intent_exists("legacy-a") is False

    reconciliation._record_terminal_submission_intent(
        local_order_id="legacy-a",
        broker_order_id="broker-legacy",
        broker_status="filled",
    )

    # Existing intent with authoritative broker ID.
    intent.claim_submission("existing-a", "NIFTY:BUY:RECONCILE")
    intent.mark_submission_started("existing-a")
    intent.record_broker_evidence(
        "existing-a", "broker-original", "submitted"
    )

    assert reconciliation._submission_intent_exists("existing-a") is True

    # Conflicting broker ID must not be ignored.
    with pytest.raises(
        ValueError,
        match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
    ):
        reconciliation._record_terminal_submission_intent(
            local_order_id="existing-a",
            broker_order_id="broker-conflicting",
            broker_status="filled",
        )

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT broker_order_id, status "
            "FROM broker_submission_intents "
            "WHERE local_order_id = 'existing-a'"
        )).one()

    assert row == ("broker-original", "submitted")

    # Terminal state must not regress to partial fill.
    intent.record_broker_evidence(
        "existing-a", "broker-original", "filled"
    )

    with pytest.raises(
        ValueError,
        match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
    ):
        intent.record_broker_evidence(
            "existing-a", "broker-original", "partially_filled"
        )

    engine.dispose()


def test_reconciliation_identity_conflict_reviews_and_continues(monkeypatch):
    """Conflicting broker identity must not corrupt unrelated orders."""
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

    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(intent, "SessionLocal", sessions)
    monkeypatch.setattr(broker_reconciliation, "SessionLocal", sessions)

    conflict_id = "ORD-CONFLICT-1"
    healthy_id = "ORD-HEALTHY-1"

    for local_id, broker_id, symbol in (
        (conflict_id, "BROKER-LOCAL-CONFLICT", "NIFTY"),
        (healthy_id, "BROKER-HEALTHY", "BANKNIFTY"),
    ):
        order_store.create_order({
            "local_order_id": local_id,
            "broker_order_id": broker_id,
            "symbol": symbol,
            "side": "BUY",
            "quantity": 10,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": "broker_submitted",
        })

    intent.claim_submission(conflict_id, "NIFTY:BUY:CONFLICT")
    intent.mark_submission_started(conflict_id)
    intent.record_broker_evidence(
        conflict_id,
        "BROKER-AUTHORITATIVE",
        "submitted",
    )

    class FakeBroker:
        async def get_positions(self):
            return [{
                "tradingSymbol": "BANKNIFTY",
                "transactionType": "BUY",
                "netQty": 10,
                "averagePrice": 101,
            }]

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol=(
                    "NIFTY"
                    if broker_order_id == "BROKER-LOCAL-CONFLICT"
                    else "BANKNIFTY"
                ),
                side="BUY",
                quantity=10,
                filled_quantity=10,
                remaining_quantity=0,
                price=101,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(
            username="conflict-review-ops",
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

    assert summary["checked_orders"] == 2
    assert summary["needs_review"] >= 1
    assert any(
        "durable broker submission identity conflict" in error
        for error in summary["errors"]
    )

    assert order_store.get_order(conflict_id)["status"] == "broker_submitted"
    assert order_store.get_order(healthy_id)["status"] == "filled"

    with engine.connect() as conn:
        durable = conn.execute(
            text(
                "SELECT broker_order_id, status "
                "FROM broker_submission_intents "
                "WHERE local_order_id = :id"
            ),
            {"id": conflict_id},
        ).one()

    assert tuple(durable) == (
        "BROKER-AUTHORITATIVE",
        "submitted",
    )


def test_reconciliation_stale_partial_fill_reviews_and_continues(monkeypatch):
    """Stale partial fill cannot reverse a durable fill or block other orders."""
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

    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(intent, "SessionLocal", sessions)
    monkeypatch.setattr(broker_reconciliation, "SessionLocal", sessions)

    stale_id = "ORD-STALE-1"
    healthy_id = "ORD-HEALTHY-STALE-1"

    for local_id, broker_id, symbol, status in (
        (stale_id, "BROKER-STALE-1", "NIFTY", "filled"),
        (healthy_id, "BROKER-HEALTHY-STALE-1", "BANKNIFTY", "broker_submitted"),
    ):
        order_store.create_order({
            "local_order_id": local_id,
            "broker_order_id": broker_id,
            "symbol": symbol,
            "side": "BUY",
            "quantity": 10,
            "entry_price": 100,
            "execution_mode": "paper",
            "status": status,
        })

    intent.claim_submission(stale_id, "NIFTY:BUY:STALE")
    intent.mark_submission_started(stale_id)
    intent.record_broker_evidence(
        stale_id, "BROKER-STALE-1", "filled"
    )

    class FakeBroker:
        async def get_positions(self):
            return [{
                "tradingSymbol": "BANKNIFTY",
                "transactionType": "BUY",
                "netQty": 10,
                "averagePrice": 101,
            }]

        async def get_order_status(self, broker_order_id):
            stale = broker_order_id == "BROKER-STALE-1"
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="partially_filled" if stale else "filled",
                symbol="NIFTY" if stale else "BANKNIFTY",
                side="BUY",
                quantity=10,
                filled_quantity=4 if stale else 10,
                remaining_quantity=6 if stale else 0,
                price=101,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(
            username="stale-state-review-ops",
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

    assert summary["checked_orders"] == 2
    assert summary["needs_review"] >= 1
    assert any(
        "stale or conflicting durable broker submission state" in error
        for error in summary["errors"]
    )

    assert order_store.get_order(stale_id)["status"] == "filled"
    assert order_store.get_order(healthy_id)["status"] == "filled"

    with engine.connect() as conn:
        durable = conn.execute(
            text(
                "SELECT broker_order_id, status "
                "FROM broker_submission_intents "
                "WHERE local_order_id = :id"
            ),
            {"id": stale_id},
        ).one()

    assert tuple(durable) == ("BROKER-STALE-1", "filled")


def test_confirmed_broker_status_does_not_create_filled_position(monkeypatch):
    """Acknowledged but unfilled broker orders must not create positions."""
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import (
        broker_reconciliation,
        order_store,
        position_store,
    )
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()

    local_id = "ORD-CONFIRMED-ZERO-FILL"
    broker_id = "BROKER-CONFIRMED-ZERO-FILL"

    order_store.create_order({
        "local_order_id": local_id,
        "broker_order_id": broker_id,
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 10,
        "entry_price": 100,
        "execution_mode": "paper",
        "status": "broker_submitted",
    })

    class FakeBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, requested_id):
            assert requested_id == broker_id
            return BrokerOrderResult(
                broker_order_id=broker_id,
                status="confirmed",
                symbol="NIFTY",
                side="BUY",
                quantity=10,
                filled_quantity=0,
                remaining_quantity=10,
                price=100,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(
            username="confirmed-zero-fill-ops",
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

    assert summary["checked_orders"] == 1
    assert order_store.get_order(local_id)["status"] != "filled"
    assert position_store.find_position_by_broker_order_id(
        broker_id,
        execution_mode="paper",
    ) is None


@pytest.mark.parametrize(
    "scenario,expected_status,expected_review",
    [
        ("crash_recovery", "rejected", False),
        ("broker_identity_mismatch", "broker_submitted", True),
    ],
)
def test_live_terminal_rejection_recovery_and_identity(
    monkeypatch, scenario, expected_status, expected_review
):
    """Recover confirmed rejection, but never trust another broker order's ID."""
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
            "('claimed', 'reconciliation_required', 'submitted', "
            "'open', 'partially_filled')"
        ))

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    local_id = f"ORD-RECOVERY-{scenario}"
    broker_id = f"BROKER-RECOVERY-{scenario}"
    logical_key = f"NIFTY:BUY:RECOVERY-{scenario}"

    order_store.create_order({
        "local_order_id": local_id,
        "broker_order_id": broker_id,
        "order_key": logical_key,
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 1,
        "entry_price": 22500,
        "execution_mode": "live",
        "status": "broker_submitted",
    })

    intent.claim_submission(local_id, logical_key)
    intent.mark_submission_started(local_id)
    intent.record_broker_evidence(local_id, broker_id, "submitted")

    if scenario == "crash_recovery":
        # Simulate a crash after durable terminal evidence was saved,
        # but before the local lifecycle order was updated.
        intent.record_broker_evidence(local_id, broker_id, "rejected")

    calls = []

    class FakeBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, requested_id):
            calls.append(requested_id)
            assert requested_id == broker_id

            returned_id = (
                "WRONG-BROKER-ID"
                if scenario == "broker_identity_mismatch"
                else broker_id
            )

            return BrokerOrderResult(
                broker_order_id=returned_id,
                status="rejected",
                symbol="NIFTY",
                side="BUY",
                quantity=1,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(
            username=f"ops-{scenario}",
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
                execution_mode="live",
            )
        )

    updated = order_store.get_order(local_id)
    assert updated["status"] == expected_status

    with engine.connect() as conn:
        durable_status = conn.execute(
            text(
                "SELECT status FROM broker_submission_intents "
                "WHERE local_order_id = :id"
            ),
            {"id": local_id},
        ).scalar_one()

    assert durable_status == (
        "rejected" if scenario == "crash_recovery" else "submitted"
    )

    assert calls == [broker_id]
    assert bool(summary["needs_review"]) is expected_review

    if expected_review:
        assert any(
            "identity mismatch" in error
            for error in summary["errors"]
        )


@pytest.mark.parametrize(
    "broker_status",
    ["rejected", "cancelled", "filled"],
)
def test_live_unconfirmed_terminal_status_preserves_durable_intent(
    monkeypatch, broker_status
):
    """Unconfirmed terminal evidence must not release a LIVE submission lock."""
    configure_sqlalchemy_store(monkeypatch)

    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from Backend.application import (
        broker_reconciliation,
        broker_submission_intent as intent,
        order_store,
        position_store,
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
            "('claimed', 'reconciliation_required', 'submitted', "
            "'open', 'partially_filled')"
        ))

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    local_id = f"ORD-UNCONFIRMED-{broker_status}"
    broker_id = f"BROKER-UNCONFIRMED-{broker_status}"
    logical_key = f"NIFTY:BUY:UNCONFIRMED-{broker_status}"

    order_store.create_order({
        "local_order_id": local_id,
        "broker_order_id": broker_id,
        "order_key": logical_key,
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 1,
        "entry_price": 22500,
        "execution_mode": "live",
        "status": "broker_submitted",
    })

    intent.claim_submission(local_id, logical_key)
    intent.mark_submission_started(local_id)
    intent.record_broker_evidence(local_id, broker_id, "submitted")

    class FakeBroker:
        async def get_positions(self):
            return []

        async def get_order_status(self, requested_id):
            assert requested_id == broker_id
            return BrokerOrderResult(
                broker_order_id=broker_id,
                status=broker_status,
                symbol="NIFTY",
                side="BUY",
                quantity=1,
                filled_quantity=0,
                confirmed=False,
            )

    with SessionLocal() as db:
        actor = User(
            username=f"ops-unconfirmed-{broker_status}",
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
                execution_mode="live",
            )
        )

    updated = order_store.get_order(local_id)
    assert updated["status"] == "broker_submitted"

    with engine.connect() as conn:
        durable_status = conn.execute(
            text(
                "SELECT status FROM broker_submission_intents "
                "WHERE local_order_id = :id"
            ),
            {"id": local_id},
        ).scalar_one()

    assert durable_status == "submitted"

    assert position_store.find_position_by_broker_order_id(
        broker_id, execution_mode="live"
    ) is None

    assert summary["fixed"] == 0
    assert summary["needs_review"] >= 1
    assert any(
        "unconfirmed terminal broker status" in error
        for error in summary["errors"]
    )
