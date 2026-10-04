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
