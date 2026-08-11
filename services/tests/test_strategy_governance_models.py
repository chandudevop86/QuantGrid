from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Backend.application.governance_service import GovernanceConflict, create_strategy_version
from Backend.core.database import Base
from Backend.domain.governance_models import ParameterSnapshot, Strategy, StrategyVersion, parameter_hash


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Strategy.__table__, ParameterSnapshot.__table__, StrategyVersion.__table__],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _version(db_session, *, version_string: str = "1.4.2") -> StrategyVersion:
    return create_strategy_version(
        db_session,
        strategy_name="AMD",
        version_string=version_string,
        parameters={"mode": "Balanced", "limits": {"max_trades": 1, "risk": 0.01}},
        git_commit_sha="a" * 40,
        git_tree_hash="b" * 64,
        git_is_clean=True,
        code_snapshot_hash="c" * 64,
        dependency_lock_hash="d" * 64,
        execution_environment_hash="e" * 64,
        created_by="test-user",
    )


def test_strategy_version_creation_persists_exact_parameter_snapshot(db_session):
    version = _version(db_session)

    assert version.strategy.name == "amd"
    assert version.version_string == "1.4.2"
    assert version.parameter_snapshot.parameter_hash == parameter_hash(
        {"limits": {"risk": 0.01, "max_trades": 1}, "mode": "Balanced"}
    )
    assert version.governance_state == "DRAFT"


def test_duplicate_strategy_version_is_rejected(db_session):
    _version(db_session)

    with pytest.raises(GovernanceConflict, match="already exists"):
        _version(db_session)


def test_version_provenance_is_immutable(db_session):
    version = _version(db_session)
    version.git_commit_sha = "f" * 40

    with pytest.raises(ValueError, match="immutable"):
        db_session.commit()


def test_parameter_snapshot_is_immutable(db_session):
    version = _version(db_session)
    version.parameter_snapshot.canonical_parameters = '{"mode":"Aggressive"}'

    with pytest.raises(ValueError, match="immutable"):
        db_session.commit()


def test_parameter_hash_is_deterministic_for_mapping_order():
    assert parameter_hash({"a": 1, "nested": {"b": True, "c": [2, 3]}}) == parameter_hash(
        {"nested": {"c": [2, 3], "b": True}, "a": 1}
    )
