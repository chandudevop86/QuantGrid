from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_FILE: Path | str = Path(os.getenv("STRATEGY_GOVERNANCE_DB_FILE", DATA_DIR / "strategy_governance.sqlite3"))
_MEMORY_CONNECTION: sqlite3.Connection | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    global _MEMORY_CONNECTION
    if str(DB_FILE) == ":memory:":
        if _MEMORY_CONNECTION is None:
            _MEMORY_CONNECTION = sqlite3.connect(":memory:", timeout=30)
            _MEMORY_CONNECTION.row_factory = sqlite3.Row
        return _MEMORY_CONNECTION
    db_file = Path(DB_FILE)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_file, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_strategy_governance_store() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_governance (
                name TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                rollout_pct INTEGER NOT NULL,
                supported_regimes_json TEXT NOT NULL,
                owner TEXT NOT NULL,
                notes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_governance_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                strategy TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def upsert_strategy_governance(row: dict[str, Any], *, overwrite: bool = True) -> dict[str, Any]:
    init_strategy_governance_store()
    normalized = _normalize_row(row)
    with _connect() as connection:
        existing = connection.execute(
            "SELECT created_at FROM strategy_governance WHERE name = ?",
            (normalized["name"],),
        ).fetchone()
        if existing and not overwrite:
            stored = get_strategy_governance(normalized["name"])
            return stored or normalized
        normalized["created_at"] = str(existing["created_at"]) if existing else utc_now()
        connection.execute(
            """
            INSERT INTO strategy_governance
            (name, version, enabled, rollout_pct, supported_regimes_json, owner, notes, created_at, updated_at)
            VALUES (:name, :version, :enabled, :rollout_pct, :supported_regimes_json, :owner, :notes, :created_at, :updated_at)
            ON CONFLICT(name) DO UPDATE SET
                version = excluded.version,
                enabled = excluded.enabled,
                rollout_pct = excluded.rollout_pct,
                supported_regimes_json = excluded.supported_regimes_json,
                owner = excluded.owner,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            normalized,
        )
    return get_strategy_governance(normalized["name"]) or _public_row(normalized)


def get_strategy_governance(name: str) -> dict[str, Any] | None:
    init_strategy_governance_store()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM strategy_governance WHERE name = ?",
            (_normalize_name(name),),
        ).fetchone()
    return _public_row(dict(row)) if row else None


def list_strategy_governance() -> list[dict[str, Any]]:
    init_strategy_governance_store()
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM strategy_governance ORDER BY name ASC").fetchall()
    return [_public_row(dict(row)) for row in rows]


from typing import Any, Dict

def record_strategy_governance_audit(event: str, strategy: str, details: dict[str, Any]) -> dict[str, Any]:
    init_strategy_governance_store()
    
    # Explicitly type row as dict[str, Any] so mypy accepts mixed type values
    row: Dict[str, Any] = {
        "event": str(event),
        "strategy": _normalize_name(strategy),
        "details_json": json.dumps(details or {}, sort_keys=True),
        "created_at": utc_now(),
    }
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO strategy_governance_audit (event, strategy, details_json, created_at)
            VALUES (:event, :strategy, :details_json, :created_at)
            """,
            row,
        )
        row["id"] = cursor.lastrowid
    return _audit_public_row(row)


def list_strategy_governance_audit(limit: int = 500) -> list[dict[str, Any]]:
    init_strategy_governance_store()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM strategy_governance_audit ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_audit_public_row(dict(row)) for row in rows]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _normalize_name(str(row.get("name") or "")),
        "version": str(row.get("version") or "1.0.0"),
        "enabled": 1 if row.get("enabled", True) else 0,
        "rollout_pct": max(0, min(100, int(row.get("rollout_pct", 100)))),
        "supported_regimes_json": json.dumps(list(row.get("supported_regimes") or ["Any"]), sort_keys=True),
        "owner": str(row.get("owner") or "quantgrid"),
        "notes": str(row.get("notes") or ""),
        "updated_at": str(row.get("updated_at") or utc_now()),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    supported_regimes = row.get("supported_regimes")
    if supported_regimes is None:
        supported_regimes = _json_list(row.get("supported_regimes_json"), default=["Any"])
    return {
        "name": _normalize_name(str(row.get("name") or "")),
        "version": str(row.get("version") or "1.0.0"),
        "enabled": bool(row.get("enabled")),
        "rollout_pct": max(0, min(100, int(row.get("rollout_pct", 100)))),
        "supported_regimes": supported_regimes,
        "owner": str(row.get("owner") or "quantgrid"),
        "notes": str(row.get("notes") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _audit_public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "event": str(row.get("event") or ""),
        "strategy": _normalize_name(str(row.get("strategy") or "")),
        "details": _json_dict(row.get("details_json")),
        "timestamp": str(row.get("created_at") or ""),
    }


def _json_list(value: Any, *, default: list[str]) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return list(default)
    if not isinstance(parsed, list):
        return list(default)
    cleaned = [str(item) for item in parsed if str(item or "").strip()]
    return cleaned or list(default)


def _json_dict(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
