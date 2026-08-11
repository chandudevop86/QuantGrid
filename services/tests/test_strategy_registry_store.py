from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Backend.application import strategy_registry_store
from Backend.core.database import Base
from Backend.domain.governance_models import Strategy, StrategyGovernanceAudit


@pytest.fixture
def registry_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Strategy.__table__, StrategyGovernanceAudit.__table__])
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(strategy_registry_store, "_legacy_store_if_requested", lambda: None)
    monkeypatch.setattr(strategy_registry_store, "_session", lambda: session_factory())
    return session_factory


def test_sqlalchemy_registry_store_is_authoritative_for_runtime_metadata(registry_db):
    saved = strategy_registry_store.upsert_strategy_governance(
        {
            "name": "AMD",
            "version": "1.4.2",
            "enabled": True,
            "rollout_pct": 75,
            "supported_regimes": ["Trending"],
            "owner": "research",
        }
    )

    assert saved["name"] == "amd"
    assert saved["version"] == "1.4.2"
    assert strategy_registry_store.get_strategy_governance("AMD")["rollout_pct"] == 75

    audit = strategy_registry_store.record_strategy_governance_audit("registered", "amd", {"source": "test"})
    assert audit["strategy"] == "amd"
    assert strategy_registry_store.list_strategy_governance_audit()[0]["details"] == {"source": "test"}
