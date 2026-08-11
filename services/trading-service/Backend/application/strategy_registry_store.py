from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from Backend.domain.governance_models import Strategy, StrategyGovernanceAudit


def _legacy_store_if_requested():
    # Legacy callers/tests may deliberately select the old isolated SQLite file.
    # Normal runtime governance uses the SQLAlchemy database below.
    from Backend.application import strategy_governance_store as legacy

    return legacy if str(legacy.DB_FILE) == ":memory:" else None


def _normalize_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(strategy: Strategy) -> dict[str, Any]:
    try:
        supported_regimes = json.loads(strategy.supported_regimes_json)
    except (TypeError, json.JSONDecodeError):
        supported_regimes = ["Any"]
    return {
        "name": strategy.name,
        "version": strategy.registry_version,
        "enabled": bool(strategy.enabled),
        "rollout_pct": int(strategy.rollout_pct),
        "supported_regimes": supported_regimes,
        "owner": strategy.owner,
        "notes": strategy.notes,
        "created_at": strategy.created_at.isoformat(),
        "updated_at": strategy.updated_at.isoformat(),
    }


def _session():
    from Backend.core.database import SessionLocal, init_database

    init_database()
    return SessionLocal()


def init_strategy_governance_store() -> None:
    legacy = _legacy_store_if_requested()
    if legacy:
        legacy.init_strategy_governance_store()
        return
    # Schema ownership remains with Alembic; this initializes only the normal
    # application database binding.
    db = _session()
    db.close()


def upsert_strategy_governance(row: dict[str, Any], *, overwrite: bool = True) -> dict[str, Any]:
    legacy = _legacy_store_if_requested()
    if legacy:
        return legacy.upsert_strategy_governance(row, overwrite=overwrite)
    name = _normalize_name(str(row.get("name") or ""))
    if not name:
        raise ValueError("Strategy governance requires a strategy name")
    db = _session()
    try:
        strategy = db.scalar(select(Strategy).where(Strategy.name == name))
        if strategy is not None and not overwrite:
            return _public(strategy)
        now = _now()
        values = {
            "display_name": str(row.get("display_name") or name),
            "registry_version": str(row.get("version") or "1.0.0"),
            "enabled": bool(row.get("enabled", True)),
            "rollout_pct": max(0, min(100, int(row.get("rollout_pct", 100)))),
            "supported_regimes_json": json.dumps(list(row.get("supported_regimes") or ["Any"]), sort_keys=True),
            "owner": str(row.get("owner") or "quantgrid"),
            "notes": str(row.get("notes") or ""),
            "updated_at": now,
        }
        if strategy is None:
            strategy = Strategy(name=name, created_at=now, **values)
            db.add(strategy)
        else:
            for field, value in values.items():
                setattr(strategy, field, value)
        db.commit()
        db.refresh(strategy)
        return _public(strategy)
    finally:
        db.close()


def get_strategy_governance(name: str) -> dict[str, Any] | None:
    legacy = _legacy_store_if_requested()
    if legacy:
        return legacy.get_strategy_governance(name)
    db = _session()
    try:
        strategy = db.scalar(select(Strategy).where(Strategy.name == _normalize_name(name)))
        return _public(strategy) if strategy else None
    finally:
        db.close()


def list_strategy_governance() -> list[dict[str, Any]]:
    legacy = _legacy_store_if_requested()
    if legacy:
        return legacy.list_strategy_governance()
    db = _session()
    try:
        rows = db.scalars(select(Strategy).order_by(Strategy.name)).all()
        return [_public(row) for row in rows]
    finally:
        db.close()


def record_strategy_governance_audit(event: str, strategy: str, details: dict[str, Any]) -> dict[str, Any]:
    legacy = _legacy_store_if_requested()
    if legacy:
        return legacy.record_strategy_governance_audit(event, strategy, details)
    name = _normalize_name(strategy)
    db = _session()
    try:
        row = db.scalar(select(Strategy).where(Strategy.name == name))
        if row is None:
            raise ValueError(f"Unknown strategy for governance audit: {name}")
        audit = StrategyGovernanceAudit(
            strategy_id=row.id,
            event=str(event),
            details_json=json.dumps(details or {}, sort_keys=True),
            created_at=_now(),
        )
        db.add(audit)
        db.commit()
        return {"id": audit.id, "event": audit.event, "strategy": name, "details": details or {}, "timestamp": audit.created_at.isoformat()}
    finally:
        db.close()


def list_strategy_governance_audit(limit: int = 500) -> list[dict[str, Any]]:
    legacy = _legacy_store_if_requested()
    if legacy:
        return legacy.list_strategy_governance_audit(limit)
    db = _session()
    try:
        rows = db.scalars(
            select(StrategyGovernanceAudit).order_by(StrategyGovernanceAudit.id.desc()).limit(max(1, min(int(limit), 500)))
        ).all()
        return [
            {
                "id": row.id,
                "event": row.event,
                "strategy": row.strategy.name,
                "details": json.loads(row.details_json),
                "timestamp": row.created_at.isoformat(),
            }
            for row in rows
        ]
    finally:
        db.close()
