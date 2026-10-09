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



def test_live_partial_fill_persists_filled_position_and_keeps_order_active(monkeypatch):
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
            return BrokerOrderResult(
                broker_order_id=broker_id, status="partially_filled", symbol="NIFTY",
                side="BUY", quantity=25, filled_quantity=10, remaining_quantity=15,
                price=101, confirmed=True,
                metadata={"super_order": {"protection": {
                    "exposed_quantity": 10, "stop_loss_present": True,
                    "stop_loss_active": True, "protected": True,
                }}},
            )

    with SessionLocal() as db:
        actor = User(username="partial-ops", password_hash="hash", role="ops")
        db.add(actor); db.commit(); db.refresh(actor)
        asyncio.run(broker_reconciliation.reconcile_broker_state(
            db=db, broker_client=PartialBroker(), actor=actor, execution_mode="live"
        ))

    updated = order_store.get_order(local_id)
    positions = position_store.list_open_positions(execution_mode="live")
    assert updated["status"] == "partially_filled"
    assert len(positions) == 1
    assert positions[0]["quantity"] == 10
    with engine.connect() as conn:
        durable = conn.execute(text(
            "SELECT status FROM broker_submission_intents WHERE local_order_id=:id"
        ), {"id": local_id}).scalar_one()
    assert durable == "partially_filled"



@pytest.mark.parametrize("missing_lookup", [False, True])
def test_live_filled_exposure_without_super_order_stop_requires_review(monkeypatch, missing_lookup):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

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


def test_live_restart_position_requires_protection_even_with_zero_reported_fill(monkeypatch):
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
