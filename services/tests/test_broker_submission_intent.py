from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from Backend.application import broker_submission_intent as intent


def test_durable_claim_and_ambiguous_boundary(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'intents.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE broker_submission_intents (local_order_id VARCHAR(120) PRIMARY KEY, logical_key VARCHAR(160) NOT NULL, correlation_id VARCHAR(120) NOT NULL UNIQUE, broker_order_id VARCHAR(120) UNIQUE, status VARCHAR(40) NOT NULL, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)'))
    with engine.begin() as conn:
        conn.execute(text("CREATE UNIQUE INDEX uq_active_intent_key ON broker_submission_intents(logical_key) WHERE status IN ('claimed', 'reconciliation_required', 'submitted', 'open', 'partially_filled')"))
    monkeypatch.setattr(intent, 'SessionLocal', sessionmaker(bind=engine))
    claim = intent.claim_submission('a', 'NIFTY:BUY:TEST')
    assert claim['status'] == 'claimed'
    with pytest.raises(ValueError, match='DUPLICATE'):
        intent.claim_submission('b', 'nifty:buy:test')
    intent.mark_submission_started('a')
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM broker_submission_intents WHERE local_order_id = 'a'")).scalar_one() == 'reconciliation_required'
    with pytest.raises(ValueError, match='NOT_CLAIMED'):
        intent.mark_submission_started('a')
    with pytest.raises(ValueError, match='AUTHORITATIVE'):
        intent.record_broker_evidence('a', '', 'rejected')
    intent.record_broker_evidence('a', 'broker-1', 'partially_filled')
    intent.record_broker_evidence('a', 'broker-1', 'filled')
    assert intent.claim_submission('b', 'NIFTY:BUY:TEST')['status'] == 'claimed'
    engine.dispose()


def test_concurrent_claim_allows_only_one_active_intent(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = create_engine(
        "sqlite:///" + str(tmp_path / "concurrent-intents.db"),
        connect_args={"check_same_thread": False, "timeout": 10},
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
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_active_intent_key "
            "ON broker_submission_intents(logical_key) "
            "WHERE status IN "
            "('claimed', 'reconciliation_required', 'submitted', 'open', 'partially_filled')"
        ))

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    barrier = Barrier(2)

    def attempt(local_order_id):
        barrier.wait()
        try:
            result = intent.claim_submission(
                local_order_id,
                "NIFTY:BUY:CONCURRENT",
            )
            return ("claimed", result["local_order_id"])
        except ValueError as exc:
            return ("rejected", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["worker-a", "worker-b"]))

    assert sum(result[0] == "claimed" for result in results) == 1
    assert sum(result[0] == "rejected" for result in results) == 1
    assert any(
        "DUPLICATE_OR_UNRESOLVED_BROKER_INTENT" in result[1]
        for result in results
        if result[0] == "rejected"
    )

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT local_order_id, status "
            "FROM broker_submission_intents "
            "WHERE logical_key = 'NIFTY:BUY:CONCURRENT'"
        )).all()

    assert len(rows) == 1
    assert rows[0][1] == "claimed"

    engine.dispose()


def test_restart_cannot_reclaim_ambiguous_submission(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "restart-intents.db"))

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
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_active_intent_key "
            "ON broker_submission_intents(logical_key) "
            "WHERE status IN "
            "('claimed', 'reconciliation_required', 'submitted', 'open', 'partially_filled')"
        ))

    # Simulate worker/process A.
    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))
    intent.claim_submission("before-restart", "NIFTY:BUY:RESTART")
    intent.mark_submission_started("before-restart")

    # Simulate a fresh worker/session after a crash or restart.
    fresh_session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(intent, "SessionLocal", fresh_session_factory)

    with pytest.raises(
        ValueError,
        match="DUPLICATE_OR_UNRESOLVED_BROKER_INTENT",
    ):
        intent.claim_submission("after-restart", "NIFTY:BUY:RESTART")

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT local_order_id, status "
            "FROM broker_submission_intents "
            "WHERE logical_key = 'NIFTY:BUY:RESTART'"
        )).all()

    assert rows == [("before-restart", "reconciliation_required")]

    engine.dispose()


def test_terminal_evidence_releases_claim_but_partial_fill_does_not(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "terminal-intents.db"))

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
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_active_intent_key "
            "ON broker_submission_intents(logical_key) "
            "WHERE status IN "
            "('claimed', 'reconciliation_required', 'submitted', 'open', 'partially_filled')"
        ))

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    # Partial fill remains active and must block another submission.
    intent.claim_submission("partial-a", "NIFTY:BUY:PARTIAL")
    intent.mark_submission_started("partial-a")
    intent.record_broker_evidence("partial-a", "broker-partial", "partially_filled")

    with pytest.raises(ValueError, match="DUPLICATE"):
        intent.claim_submission("partial-b", "NIFTY:BUY:PARTIAL")

    # Filled is terminal and releases the logical key.
    intent.record_broker_evidence("partial-a", "broker-partial", "filled")
    assert intent.claim_submission(
        "filled-retry",
        "NIFTY:BUY:PARTIAL",
    )["status"] == "claimed"

    # Rejected is also terminal and releases its logical key.
    intent.claim_submission("reject-a", "BANKNIFTY:BUY:REJECT")
    intent.mark_submission_started("reject-a")
    intent.record_broker_evidence("reject-a", "broker-reject", "rejected")

    assert intent.claim_submission(
        "reject-b",
        "BANKNIFTY:BUY:REJECT",
    )["status"] == "claimed"

    engine.dispose()
