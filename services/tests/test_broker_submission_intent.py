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
    # Dhan Super Order API limits correlationId to 30 safe characters.
    assert claim['correlation_id'].startswith('QG-')
    assert len(claim['correlation_id']) <= 30
    assert claim['correlation_id'].isascii()
    assert claim['correlation_id'].replace('-', '').isalnum()
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


def test_conflicting_broker_evidence_cannot_overwrite_intent(tmp_path, monkeypatch):
    """Conflicting broker IDs must never replace previously recorded evidence."""
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "conflicting-evidence.db")
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

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    intent.claim_submission("conflict-a", "NIFTY:BUY:CONFLICT")
    intent.mark_submission_started("conflict-a")

    # First authoritative evidence is accepted.
    intent.record_broker_evidence(
        "conflict-a", "broker-original", "submitted"
    )

    # Simulate a later reconciliation-required state without erasing evidence.
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE broker_submission_intents "
            "SET status = 'reconciliation_required' "
            "WHERE local_order_id = 'conflict-a'"
        ))

    # Conflicting broker evidence must fail closed.
    with pytest.raises(
        ValueError,
        match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
    ):
        intent.record_broker_evidence(
            "conflict-a", "broker-conflicting", "filled"
        )

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT broker_order_id, status "
            "FROM broker_submission_intents "
            "WHERE local_order_id = 'conflict-a'"
        )).one()

    assert row == ("broker-original", "reconciliation_required")

    # Matching evidence remains acceptable during reconciliation.
    intent.record_broker_evidence(
        "conflict-a", "broker-original", "filled"
    )

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT broker_order_id, status "
            "FROM broker_submission_intents "
            "WHERE local_order_id = 'conflict-a'"
        )).one()

    assert row == ("broker-original", "filled")
    engine.dispose()


def test_stale_broker_evidence_cannot_regress_intent(tmp_path, monkeypatch):
    """Older broker responses cannot move a durable intent backward."""
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "stale-evidence.db")
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

    monkeypatch.setattr(intent, "SessionLocal", sessionmaker(bind=engine))

    intent.claim_submission("stale-a", "NIFTY:BUY:STALE")
    intent.mark_submission_started("stale-a")
    intent.record_broker_evidence("stale-a", "broker-stale", "submitted")
    intent.record_broker_evidence("stale-a", "broker-stale", "open")
    intent.record_broker_evidence("stale-a", "broker-stale", "partially_filled")

    for stale_status in ("submitted", "open", "rejected"):
        with pytest.raises(
            ValueError,
            match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
        ):
            intent.record_broker_evidence(
                "stale-a", "broker-stale", stale_status
            )

    with engine.connect() as conn:
        status = conn.execute(text(
            "SELECT status FROM broker_submission_intents "
            "WHERE local_order_id = 'stale-a'"
        )).scalar_one()

    assert status == "partially_filled"

    intent.record_broker_evidence("stale-a", "broker-stale", "filled")

    with pytest.raises(
        ValueError,
        match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
    ):
        intent.record_broker_evidence(
            "stale-a", "broker-stale", "submitted"
        )

    with engine.connect() as conn:
        status = conn.execute(text(
            "SELECT status FROM broker_submission_intents "
            "WHERE local_order_id = 'stale-a'"
        )).scalar_one()

    assert status == "filled"
    engine.dispose()



@pytest.mark.parametrize(
    "terminal_status,conflicting_status",
    [
        ("filled", "cancelled"),
        ("cancelled", "filled"),
        ("rejected", "filled"),
    ],
)
def test_terminal_broker_evidence_is_idempotent_and_identity_locked(
    tmp_path, monkeypatch, terminal_status, conflicting_status
):
    """Repeated terminal evidence is safe; conflicting evidence is rejected."""
    from sqlalchemy import text
    from Backend.application import broker_submission_intent as intent

    engine = create_engine(
        "sqlite:///" + str(tmp_path / "terminal-idempotency.db")
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
            "('claimed', 'reconciliation_required', "
            "'submitted', 'open', 'partially_filled')"
        ))

    monkeypatch.setattr(
        intent, "SessionLocal", sessionmaker(bind=engine)
    )

    local_id = f"terminal-idempotent-{terminal_status}"
    broker_id = f"broker-idempotent-{terminal_status}"

    intent.claim_submission(local_id, f"KEY:{terminal_status}")
    intent.mark_submission_started(local_id)

    intent.record_broker_evidence(
        local_id, broker_id, terminal_status
    )

    # Repeating the identical authoritative evidence must succeed.
    intent.record_broker_evidence(
        local_id, broker_id, terminal_status
    )

    with pytest.raises(
        ValueError,
        match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
    ):
        intent.record_broker_evidence(
            local_id, f"{broker_id}-OTHER", terminal_status
        )

    with pytest.raises(
        ValueError,
        match="BROKER_INTENT_NOT_AWAITING_RECONCILIATION",
    ):
        intent.record_broker_evidence(
            local_id, broker_id, conflicting_status
        )

    with intent.SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT broker_order_id, status "
                "FROM broker_submission_intents "
                "WHERE local_order_id = :id"
            ),
            {"id": local_id},
        ).one()

    assert tuple(row) == (broker_id, terminal_status)
