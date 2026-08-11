from __future__ import annotations

from typing import Any

from sqlalchemy import select

from Backend.domain.governance_models import ParameterSnapshot, Strategy, StrategyVersion, canonical_json, parameter_hash, parameter_schema_hash


class GovernanceConflict(ValueError):
    pass


def create_strategy_version(
    db,
    *,
    strategy_name: str,
    version_string: str,
    parameters: Any,
    git_commit_sha: str,
    git_tree_hash: str,
    git_is_clean: bool,
    code_snapshot_hash: str,
    dependency_lock_hash: str,
    execution_environment_hash: str,
    created_by: str,
    reproducibility_status: str | None = None,
    display_name: str | None = None,
) -> StrategyVersion:
    """Register a new immutable research artifact; never updates an existing version."""
    name = strategy_name.strip().lower().replace("-", "_").replace(" ", "_")
    strategy = db.scalar(select(Strategy).where(Strategy.name == name))
    if strategy is None:
        strategy = Strategy(name=name, display_name=display_name)
        db.add(strategy)
        db.flush()
    duplicate = db.scalar(select(StrategyVersion).where(
        StrategyVersion.strategy_id == strategy.id,
        StrategyVersion.version_string == version_string,
    ))
    if duplicate:
        raise GovernanceConflict(f"Strategy version already exists: {name} {version_string}")
    canonical_parameters = canonical_json(parameters)
    parameters_digest = parameter_hash(parameters)
    snapshot = db.scalar(
        select(ParameterSnapshot).where(ParameterSnapshot.parameter_hash == parameters_digest)
    )
    if snapshot is None:
        snapshot = ParameterSnapshot(
            canonical_parameters=canonical_parameters,
            parameter_hash=parameters_digest,
            schema_hash=parameter_schema_hash(parameters),
        )
        db.add(snapshot)
        db.flush()
    elif snapshot.canonical_parameters != canonical_parameters:
        raise GovernanceConflict("Parameter hash collision detected")
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_string=version_string,
        git_commit_sha=git_commit_sha,
        git_tree_hash=git_tree_hash,
        git_is_clean=bool(git_is_clean),
        reproducibility_status=reproducibility_status or ("REPRODUCIBLE" if git_is_clean else "NON_REPRODUCIBLE"),
        code_snapshot_hash=code_snapshot_hash,
        dependency_lock_hash=dependency_lock_hash,
        execution_environment_hash=execution_environment_hash,
        parameter_schema_hash=snapshot.schema_hash,
        parameter_snapshot_id=snapshot.id,
        created_by=created_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def create_verified_strategy_version(
    db,
    *,
    strategy_name: str,
    version_string: str,
    parameters: Any,
    created_by: str,
    requested_commit_sha: str | None = None,
    repository_root: str | None = None,
    display_name: str | None = None,
) -> StrategyVersion:
    """Create a version only from locally verified Git/environment provenance."""
    from Backend.application.git_verification_service import GitVerificationService

    provenance = GitVerificationService(repository_root).capture(
        requested_commit_sha=requested_commit_sha
    )
    return create_strategy_version(
        db,
        strategy_name=strategy_name,
        version_string=version_string,
        parameters=parameters,
        git_commit_sha=provenance.head_commit_sha,
        git_tree_hash=provenance.git_tree_hash,
        git_is_clean=provenance.git_is_clean,
        reproducibility_status=provenance.reproducibility_status,
        code_snapshot_hash=provenance.code_snapshot_hash,
        dependency_lock_hash=provenance.dependency_lock_hash,
        execution_environment_hash=provenance.execution_environment_hash,
        created_by=created_by,
        display_name=display_name,
    )