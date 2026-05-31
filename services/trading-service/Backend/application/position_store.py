from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Backend.application.market_data_store import latest_candles
from Backend.application.paper_trade_store import DATA_DIR


DB_FILE = DATA_DIR / "positions.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_position_store() -> None:
    if not _use_sqlite():
        _init_db_store()
        return
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker_order_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                target REAL,
                current_price REAL,
                exit_price REAL,
                exit_reason TEXT,
                open_pnl REAL NOT NULL DEFAULT 0,
                closed_pnl REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(positions)").fetchall()
        }
        if "exit_price" not in columns:
            connection.execute("ALTER TABLE positions ADD COLUMN exit_price REAL")
        if "exit_reason" not in columns:
            connection.execute("ALTER TABLE positions ADD COLUMN exit_reason TEXT")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_positions_status_updated
            ON positions(status, updated_at DESC)
            """
        )


def create_open_position(payload: dict[str, Any]) -> dict[str, Any]:
    init_position_store()
    if not _use_sqlite():
        return _db_create_open_position(payload)
    now = utc_now()
    symbol = str(payload.get("symbol") or "").upper()
    side = str(payload.get("side") or "").upper()
    quantity = int(payload.get("quantity") or 0)
    entry = float(payload.get("entry_price") or payload.get("entry") or 0.0)
    current = float(payload.get("current_price") or entry)
    row = {
        "broker_order_id": payload.get("broker_order_id"),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry_price": entry,
        "stop_loss": float(payload.get("stop_loss") or 0.0),
        "target": float(payload.get("target") or payload.get("target_price") or 0.0),
        "current_price": current,
        "exit_price": None,
        "exit_reason": None,
        "open_pnl": _open_pnl(side, quantity, entry, current),
        "closed_pnl": 0.0,
        "status": "open",
        "opened_at": str(payload.get("opened_at") or now),
        "closed_at": None,
        "updated_at": now,
    }
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO positions
                (broker_order_id, symbol, side, quantity, entry_price, stop_loss, target, current_price,
                 exit_price, exit_reason, open_pnl, closed_pnl, status, opened_at, closed_at, updated_at)
            VALUES
                (:broker_order_id, :symbol, :side, :quantity, :entry_price, :stop_loss, :target, :current_price,
                 :exit_price, :exit_reason, :open_pnl, :closed_pnl, :status, :opened_at, :closed_at, :updated_at)
            """,
            row,
        )
        row["id"] = cursor.lastrowid
    return row


def list_open_positions() -> list[dict[str, Any]]:
    init_position_store()
    if not _use_sqlite():
        _db_refresh_open_positions()
        return _db_list_positions("open")
    _refresh_open_positions()
    return _list_positions("open")


def list_closed_positions(limit: int = 100) -> list[dict[str, Any]]:
    init_position_store()
    if not _use_sqlite():
        return _db_list_positions("closed", limit=limit)
    return _list_positions("closed", limit=limit)


def find_position_by_broker_order_id(broker_order_id: str) -> dict[str, Any] | None:
    init_position_store()
    if not _use_sqlite():
        return _db_find_position_by_broker_order_id(broker_order_id)
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM positions
            WHERE broker_order_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (broker_order_id,),
        ).fetchone()
    return dict(row) if row else None


def get_position(position_id: int) -> dict[str, Any] | None:
    init_position_store()
    if not _use_sqlite():
        return _db_get_position(position_id)
    with _connect() as connection:
        row = connection.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    return dict(row) if row else None


def update_open_position(position_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    init_position_store()
    if not _use_sqlite():
        return _db_update_open_position(position_id, payload)
    allowed = {
        "broker_order_id",
        "symbol",
        "side",
        "quantity",
        "entry_price",
        "stop_loss",
        "target",
        "current_price",
    }
    updates: list[str] = []
    values: list[Any] = []
    with _connect() as connection:
        existing = connection.execute(
            "SELECT * FROM positions WHERE id = ? AND status = 'open'",
            (position_id,),
        ).fetchone()
        if existing is None:
            return None
        merged = dict(existing)
        for key in allowed:
            if key not in payload:
                continue
            updates.append(f"{key} = ?")
            values.append(payload[key])
            merged[key] = payload[key]
        if not updates:
            return dict(existing)
        current = float(merged.get("current_price") or merged.get("entry_price") or 0.0)
        entry = float(merged.get("entry_price") or current)
        side = str(merged.get("side") or "BUY")
        quantity = int(merged.get("quantity") or 0)
        updates.append("open_pnl = ?")
        values.append(_open_pnl(side, quantity, entry, current))
        updates.append("updated_at = ?")
        values.append(utc_now())
        values.append(position_id)
        connection.execute(
            f"UPDATE positions SET {', '.join(updates)} WHERE id = ? AND status = 'open'",
            values,
        )
        row = connection.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    return dict(row) if row else None


def close_open_position(position_id: int, *, current_price: float | None = None, reason: str | None = None) -> dict[str, Any] | None:
    init_position_store()
    if not _use_sqlite():
        return _db_close_open_position(position_id, current_price=current_price, reason=reason)
    now = utc_now()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM positions WHERE id = ? AND status = 'open'",
            (position_id,),
        ).fetchone()
        if row is None:
            return None
        exit_price = float(current_price if current_price is not None else row["current_price"] or row["entry_price"])
        closed_pnl = _open_pnl(str(row["side"]), int(row["quantity"]), float(row["entry_price"]), exit_price)
        connection.execute(
            """
            UPDATE positions
            SET status = 'closed', current_price = ?, exit_price = ?, exit_reason = ?,
                open_pnl = 0, closed_pnl = ?,
                closed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (exit_price, exit_price, reason, closed_pnl, now, now, position_id),
        )
        updated = connection.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    return dict(updated) if updated else None


def position_summary() -> dict[str, Any]:
    open_positions = list_open_positions()
    closed_positions = list_closed_positions(500)
    today = datetime.now(timezone.utc).date().isoformat()
    realized_today = sum(float(item.get("closed_pnl") or 0.0) for item in closed_positions if str(item.get("closed_at") or "").startswith(today))
    unrealized = sum(float(item.get("open_pnl") or 0.0) for item in open_positions)
    exposure = sum(abs(float(item.get("current_price") or item.get("entry_price") or 0.0) * int(item.get("quantity") or 0)) for item in open_positions)
    realized_total = sum(float(item.get("closed_pnl") or 0.0) for item in closed_positions)
    return {
        "open_positions": len(open_positions),
        "closed_positions": len(closed_positions),
        "current_exposure": round(exposure, 2),
        "realized_pnl": round(realized_total, 2),
        "unrealized_pnl": round(unrealized, 2),
        "todays_pnl": round(realized_today + unrealized, 2),
    }


def _list_positions(status: str, *, limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM positions
            WHERE status = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (status, max(1, min(int(limit), 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def _refresh_open_positions() -> None:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM positions WHERE status = 'open'").fetchall()
        for row in rows:
            current = _latest_price(row["symbol"]) or float(row["current_price"] or row["entry_price"])
            pnl = _open_pnl(str(row["side"]), int(row["quantity"]), float(row["entry_price"]), current)
            connection.execute(
                "UPDATE positions SET current_price = ?, open_pnl = ?, updated_at = ? WHERE id = ?",
                (current, pnl, utc_now(), row["id"]),
            )


def _latest_price(symbol: str) -> float | None:
    candles = latest_candles(symbol, "1m", 1)
    if not candles:
        return None
    try:
        return float(candles[-1].get("close"))
    except (TypeError, ValueError):
        return None


def _open_pnl(side: str, quantity: int, entry: float, current: float) -> float:
    multiplier = 1.0 if side.upper() == "BUY" else -1.0
    return round((float(current) - float(entry)) * multiplier * int(quantity), 2)


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _init_db_store() -> None:
    from sqlalchemy import inspect, text

    from Backend.core.database import Base, engine
    import Backend.domain.trading_store_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("positions")}
    additions = {
        "exit_price": "ALTER TABLE positions ADD COLUMN exit_price FLOAT",
        "exit_reason": "ALTER TABLE positions ADD COLUMN exit_reason VARCHAR(80)",
    }
    with engine.begin() as connection:
        for column, statement in additions.items():
            if column not in columns:
                connection.execute(text(statement))


def _position_row(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    symbol = str(payload.get("symbol") or "").upper()
    side = str(payload.get("side") or "").upper()
    quantity = int(payload.get("quantity") or 0)
    entry = float(payload.get("entry_price") or payload.get("entry") or 0.0)
    current = float(payload.get("current_price") or entry)
    return {
        "broker_order_id": payload.get("broker_order_id"),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry_price": entry,
        "stop_loss": float(payload.get("stop_loss") or 0.0),
        "target": float(payload.get("target") or payload.get("target_price") or 0.0),
        "current_price": current,
        "exit_price": None,
        "exit_reason": None,
        "open_pnl": _open_pnl(side, quantity, entry, current),
        "closed_pnl": 0.0,
        "status": "open",
        "opened_at": str(payload.get("opened_at") or now),
        "closed_at": None,
        "updated_at": now,
    }


def _record_to_dict(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "broker_order_id": record.broker_order_id,
        "symbol": record.symbol,
        "side": record.side,
        "quantity": record.quantity,
        "entry_price": record.entry_price,
        "stop_loss": record.stop_loss,
        "target": record.target,
        "current_price": record.current_price,
        "exit_price": record.exit_price,
        "exit_reason": record.exit_reason,
        "open_pnl": record.open_pnl,
        "closed_pnl": record.closed_pnl,
        "status": record.status,
        "opened_at": record.opened_at,
        "closed_at": record.closed_at,
        "updated_at": record.updated_at,
    }


def _db_create_open_position(payload: dict[str, Any]) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    row = _position_row(payload)
    with SessionLocal() as db:
        record = PositionRecord(**row)
        db.add(record)
        db.commit()
        db.refresh(record)
        return _record_to_dict(record)


def _db_list_positions(status: str, *, limit: int = 100) -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    with SessionLocal() as db:
        rows = db.query(PositionRecord).filter(PositionRecord.status == status).order_by(PositionRecord.updated_at.desc(), PositionRecord.id.desc()).limit(max(1, min(int(limit), 500))).all()
        return [_record_to_dict(row) for row in rows]


def _db_find_position_by_broker_order_id(broker_order_id: str) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    with SessionLocal() as db:
        row = db.query(PositionRecord).filter(PositionRecord.broker_order_id == broker_order_id).order_by(PositionRecord.updated_at.desc(), PositionRecord.id.desc()).first()
        return _record_to_dict(row) if row else None


def _db_get_position(position_id: int) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    with SessionLocal() as db:
        row = db.query(PositionRecord).filter(PositionRecord.id == position_id).first()
        return _record_to_dict(row) if row else None


def _db_update_open_position(position_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    allowed = {"broker_order_id", "symbol", "side", "quantity", "entry_price", "stop_loss", "target", "current_price"}
    with SessionLocal() as db:
        row = db.query(PositionRecord).filter(PositionRecord.id == position_id, PositionRecord.status == "open").first()
        if row is None:
            return None
        for key in allowed:
            if key in payload:
                setattr(row, key, payload[key])
        current = float(row.current_price or row.entry_price or 0.0)
        row.open_pnl = _open_pnl(str(row.side), int(row.quantity), float(row.entry_price), current)
        row.updated_at = utc_now()
        db.commit()
        db.refresh(row)
        return _record_to_dict(row)


def _db_close_open_position(position_id: int, *, current_price: float | None = None, reason: str | None = None) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    with SessionLocal() as db:
        row = db.query(PositionRecord).filter(PositionRecord.id == position_id, PositionRecord.status == "open").first()
        if row is None:
            return None
        exit_price = float(current_price if current_price is not None else row.current_price or row.entry_price)
        row.status = "closed"
        row.current_price = exit_price
        row.exit_price = exit_price
        row.exit_reason = reason
        row.open_pnl = 0.0
        row.closed_pnl = _open_pnl(str(row.side), int(row.quantity), float(row.entry_price), exit_price)
        row.closed_at = utc_now()
        row.updated_at = row.closed_at
        db.commit()
        db.refresh(row)
        return _record_to_dict(row)


def _db_refresh_open_positions() -> None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PositionRecord

    with SessionLocal() as db:
        rows = db.query(PositionRecord).filter(PositionRecord.status == "open").all()
        for row in rows:
            current = _latest_price(row.symbol) or float(row.current_price or row.entry_price)
            row.current_price = current
            row.open_pnl = _open_pnl(str(row.side), int(row.quantity), float(row.entry_price), current)
            row.updated_at = utc_now()
        db.commit()
