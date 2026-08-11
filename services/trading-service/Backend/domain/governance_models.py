from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.core.database import Base

GOVERNANCE_STATES = {
    "DRAFT", "REGISTERED", "BACKTEST_RUNNING", "BACKTEST_PASSED", "OOS_PASSED",
    "WALK_FORWARD_PASSED", "ROBUSTNESS_PASSED", "PAPER_TRADING", "PAPER_PASSED",
    "APPROVAL_PENDING", "PRODUCTION_APPROVED", "DEPLOYED", "RETIRED",
    "BACKTEST_FAILED", "OOS_FAILED", "WALK_FORWARD_FAILED", "ROBUSTNESS_FAILED",
    "PAPER_FAILED", "REJECTED",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parameter_hash(parameters: Any) -> str:
    return sha256_text(canonical_json(parameters))


def parameter_schema_hash(parameters: Any) -> str:
    if isinstance(parameters, dict):
        schema = {str(key): type(value).__name__ for key, value in sorted(parameters.items())}
    else:
        schema = {"type": type(parameters).__name__}
    return sha256_text(canonical_json(schema))


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    registry_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rollout_pct: Mapped[int] = mapped_column(nullable=False, default=100)
    supported_regimes_json: Mapped[str] = mapped_column(Text, nullable=False, default='["Any"]')
    owner: Mapped[str] = mapped_column(String(120), nullable=False, default="quantgrid")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    versions: Mapped[list["StrategyVersion"]] = relationship(back_populates="strategy")
    governance_audits: Mapped[list["StrategyGovernanceAudit"]] = relationship(back_populates="strategy")


class StrategyGovernanceAudit(Base):
    __tablename__ = "strategy_governance_audit"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    strategy: Mapped[Strategy] = relationship(back_populates="governance_audits")


class ParameterSnapshot(Base):
    __tablename__ = "parameter_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    canonical_parameters: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    strategy_versions: Mapped[list["StrategyVersion"]] = relationship(back_populates="parameter_snapshot")


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version_string", name="uq_strategy_version_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False, index=True)
    version_string: Mapped[str] = mapped_column(String(80), nullable=False)
    git_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    git_tree_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    git_is_clean: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reproducibility_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NON_REPRODUCIBLE")
    code_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_lock_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_environment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_snapshot_id: Mapped[str] = mapped_column(ForeignKey("parameter_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    governance_state: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT", index=True)
    strategy: Mapped[Strategy] = relationship(back_populates="versions")
    parameter_snapshot: Mapped[ParameterSnapshot] = relationship(back_populates="strategy_versions")


_IMMUTABLE_VERSION_FIELDS = {
    "strategy_id", "version_string", "git_commit_sha", "git_tree_hash", "git_is_clean",
    "reproducibility_status", "code_snapshot_hash", "dependency_lock_hash", "execution_environment_hash",
    "parameter_schema_hash", "parameter_snapshot_id", "created_at", "created_by",
}


@event.listens_for(StrategyVersion, "before_update")
def _reject_version_provenance_mutation(_mapper, _connection, target: StrategyVersion) -> None:
    state = inspect(target)
    changed = {name for name in _IMMUTABLE_VERSION_FIELDS if state.attrs[name].history.has_changes()}
    if changed:
        raise ValueError(f"StrategyVersion provenance is immutable: {', '.join(sorted(changed))}")
    if target.governance_state not in GOVERNANCE_STATES:
        raise ValueError(f"Unknown governance state: {target.governance_state}")


@event.listens_for(ParameterSnapshot, "before_update")
def _reject_parameter_mutation(_mapper, _connection, target: ParameterSnapshot) -> None:
    state = inspect(target)
    if any(state.attrs[name].history.has_changes() for name in ("canonical_parameters", "parameter_hash", "schema_hash", "created_at")):
        raise ValueError("ParameterSnapshot is immutable")
