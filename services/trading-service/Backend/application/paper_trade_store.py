from __future__ import annotations

import os
import sqlite3
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_FILE = Path(os.getenv("PAPER_TRADE_DB_FILE", DATA_DIR / "paper_trades.sqlite3"))
_init_lock = threading.Lock()
_initialized_store_key: tuple[str, object] | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_paper_trade_store() -> None:
    global _initialized_store_key

    store_key = _paper_trade_store_key()
    if _initialized_store_key == store_key:
        return

    with _init_lock:
        store_key = _paper_trade_store_key()
        if _initialized_store_key == store_key:
            return
        _initialize_paper_trade_store()
        _initialized_store_key = store_key


def _paper_trade_store_key() -> tuple[str, object]:
    if _use_sqlite():
        return ("sqlite", str(DB_FILE.resolve()))
    from Backend.core.database import engine

    return ("sqlalchemy", engine)


def _initialize_paper_trade_store() -> None:
    if not _use_sqlite():
        _init_db_store()
        return
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target REAL NOT NULL,
                trailing_stop_loss REAL,
                trailing_stop_pct REAL,
                status TEXT NOT NULL,
                pnl REAL NOT NULL DEFAULT 0,
                reason TEXT,
                broker_order_id TEXT,
                broker_status TEXT,
                raw_safe_broker_response TEXT,
                score REAL NOT NULL DEFAULT 0,
                regime TEXT,
                signal_time TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_paper_trades_created
            ON paper_trades(created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                signal TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'recorded',
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target REAL NOT NULL,
                exit_price REAL,
                pnl REAL NOT NULL DEFAULT 0,
                quantity INTEGER,
                reason TEXT,
                exit_reason TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                closed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_journal_created
            ON trade_journal(created_at DESC)
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(paper_trades)").fetchall()
        }
        if "broker_order_id" not in columns:
            connection.execute("ALTER TABLE paper_trades ADD COLUMN broker_order_id TEXT")
        if "broker_status" not in columns:
            connection.execute("ALTER TABLE paper_trades ADD COLUMN broker_status TEXT")
        if "raw_safe_broker_response" not in columns:
            connection.execute("ALTER TABLE paper_trades ADD COLUMN raw_safe_broker_response TEXT")
        if "trailing_stop_loss" not in columns:
            connection.execute("ALTER TABLE paper_trades ADD COLUMN trailing_stop_loss REAL")
        if "trailing_stop_pct" not in columns:
            connection.execute("ALTER TABLE paper_trades ADD COLUMN trailing_stop_pct REAL")
        journal_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(trade_journal)").fetchall()
        }
        journal_additions = {
            "status": "ALTER TABLE trade_journal ADD COLUMN status TEXT NOT NULL DEFAULT 'recorded'",
            "quantity": "ALTER TABLE trade_journal ADD COLUMN quantity INTEGER",
            "reason": "ALTER TABLE trade_journal ADD COLUMN reason TEXT",
            "source": "ALTER TABLE trade_journal ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
        }
        for column, statement in journal_additions.items():
            if column not in journal_columns:
                connection.execute(statement)


def create_paper_trade(payload: dict[str, Any]) -> dict[str, Any]:
    init_paper_trade_store()
    if not _use_sqlite():
        return _db_create_paper_trade(payload)
    created_at = str(payload.get("created_at") or utc_now())
    row = {
        "strategy": str(payload.get("strategy") or payload.get("strategy_name") or "unknown"),
        "symbol": str(payload.get("symbol") or "").upper(),
        "side": str(payload.get("side") or "").upper(),
        "entry": float(payload.get("entry") or payload.get("entry_price") or 0.0),
        "stop_loss": float(payload.get("stop_loss") or 0.0),
        "target": float(payload.get("target") or payload.get("target_price") or 0.0),
        "trailing_stop_loss": _float_or_none(payload.get("trailing_stop_loss")),
        "trailing_stop_pct": _float_or_none(payload.get("trailing_stop_pct")),
        "status": str(payload.get("status") or "paper_simulated"),
        "pnl": float(payload.get("pnl") or 0.0),
        "reason": payload.get("reason"),
        "broker_order_id": payload.get("broker_order_id"),
        "broker_status": payload.get("broker_status"),
        "raw_safe_broker_response": _json_or_none(payload.get("raw_safe_broker_response")),
        "score": float(payload.get("score") or 0.0),
        "regime": payload.get("regime"),
        "signal_time": payload.get("signal_time"),
        "created_at": created_at,
    }
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO paper_trades
                (strategy, symbol, side, entry, stop_loss, target, trailing_stop_loss, trailing_stop_pct, status, pnl, reason, broker_order_id, broker_status, raw_safe_broker_response, score, regime, signal_time, created_at)
            VALUES
                (:strategy, :symbol, :side, :entry, :stop_loss, :target, :trailing_stop_loss, :trailing_stop_pct, :status, :pnl, :reason, :broker_order_id, :broker_status, :raw_safe_broker_response, :score, :regime, :signal_time, :created_at)
            """,
            row,
        )
        row["id"] = cursor.lastrowid
    _record_trade_journal_from_paper_trade(row)
    return row


def list_paper_trades(limit: int = 100) -> list[dict[str, Any]]:
    init_paper_trade_store()
    if not _use_sqlite():
        return _db_list_paper_trades(limit)
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM paper_trades ORDER BY created_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [dict(row) for row in rows]


def update_paper_trade_status(
    broker_order_id: str,
    *,
    status: str,
    reason: str | None = None,
    pnl: float | None = None,
    broker_status: str | None = None,
    raw_safe_broker_response: Any | None = None,
) -> dict[str, Any] | None:
    init_paper_trade_store()
    if not _use_sqlite():
        return _db_update_paper_trade_status(
            broker_order_id,
            status=status,
            reason=reason,
            pnl=pnl,
            broker_status=broker_status,
            raw_safe_broker_response=raw_safe_broker_response,
        )
    updates = ["status = ?"]
    values: list[Any] = [status]
    if reason is not None:
        updates.append("reason = ?")
        values.append(reason)
    if pnl is not None:
        updates.append("pnl = ?")
        values.append(float(pnl))
    if broker_status is not None:
        updates.append("broker_status = ?")
        values.append(broker_status)
    if raw_safe_broker_response is not None:
        updates.append("raw_safe_broker_response = ?")
        values.append(_json_or_none(raw_safe_broker_response))
    values.append(broker_order_id)
    with _connect() as connection:
        connection.execute(
            f"UPDATE paper_trades SET {', '.join(updates)} WHERE broker_order_id = ?",
            values,
        )
        row = connection.execute(
            "SELECT * FROM paper_trades WHERE broker_order_id = ? ORDER BY id DESC LIMIT 1",
            (broker_order_id,),
        ).fetchone()
    return dict(row) if row else None


def calculate_paper_trade_pnl(
    *,
    side: str,
    entry: float,
    exit_price: float,
    quantity: int = 1,
    partial_quantity: int | None = None,
) -> float:
    effective_quantity = int(partial_quantity if partial_quantity is not None else quantity)
    direction = 1 if str(side).upper() in {"BUY", "CE", "CALL"} else -1
    return round((float(exit_price) - float(entry)) * effective_quantity * direction, 2)


def resolve_paper_trade_outcome(trade: dict[str, Any], market_price: float) -> dict[str, Any]:
    side = str(trade.get("side") or trade.get("signal") or "BUY").upper()
    entry = float(trade.get("entry") or trade.get("entry_price") or 0.0)
    stop_loss = float(trade.get("stop_loss") or 0.0)
    target = float(trade.get("target") or trade.get("target_price") or 0.0)
    quantity = int(trade.get("quantity") or 1)
    price = float(market_price)
    is_long = side in {"BUY", "CE", "CALL"}

    if is_long and stop_loss > 0 and price <= stop_loss:
        status, result, reason = "closed", "loss", "stop_loss_hit"
    elif is_long and target > 0 and price >= target:
        status, result, reason = "closed", "win", "target_hit"
    elif not is_long and stop_loss > 0 and price >= stop_loss:
        status, result, reason = "closed", "loss", "stop_loss_hit"
    elif not is_long and target > 0 and price <= target:
        status, result, reason = "closed", "win", "target_hit"
    else:
        status, result, reason = str(trade.get("status") or "open"), "open", "still_open"

    pnl = calculate_paper_trade_pnl(side=side, entry=entry, exit_price=price, quantity=quantity)
    return {
        **trade,
        "status": status,
        "result": result,
        "exit_price": price if status == "closed" else trade.get("exit_price"),
        "pnl": pnl if status == "closed" else float(trade.get("pnl") or 0.0),
        "exit_reason": reason,
    }


def manual_exit_payload(trade: dict[str, Any], *, exit_price: float, quantity: int | None = None, reason: str = "manual_exit") -> dict[str, Any]:
    trade_quantity = int(trade.get("quantity") or 1)
    exit_quantity = int(quantity or trade_quantity)
    partial = exit_quantity < trade_quantity
    pnl = calculate_paper_trade_pnl(
        side=str(trade.get("side") or trade.get("signal") or "BUY"),
        entry=float(trade.get("entry") or trade.get("entry_price") or 0.0),
        exit_price=float(exit_price),
        quantity=trade_quantity,
        partial_quantity=exit_quantity,
    )
    return {
        **trade,
        "status": "partially_exited" if partial else "closed",
        "exit_price": float(exit_price),
        "quantity": trade_quantity - exit_quantity if partial else trade_quantity,
        "exit_quantity": exit_quantity,
        "pnl": pnl,
        "result": "win" if pnl > 0 else "loss" if pnl < 0 else "flat",
        "exit_reason": reason,
        "closed_at": utc_now() if not partial else trade.get("closed_at"),
    }


def create_trade_journal_entry(payload: dict[str, Any]) -> dict[str, Any]:
    init_paper_trade_store()
    row = {
        "strategy": str(payload.get("strategy") or payload.get("strategy_name") or "unknown"),
        "signal": str(payload.get("signal") or payload.get("side") or "UNKNOWN").upper(),
        "symbol": str(payload.get("symbol") or "NIFTY").upper(),
        "status": str(payload.get("status") or "recorded").lower(),
        "entry": float(payload.get("entry") or payload.get("entry_price") or 0.0),
        "stop_loss": float(payload.get("stop_loss") or 0.0),
        "target": float(payload.get("target") or payload.get("target_price") or 0.0),
        "exit_price": _float_or_none(payload.get("exit_price")),
        "pnl": float(payload.get("pnl") or 0.0),
        "quantity": int(payload["quantity"]) if payload.get("quantity") not in {None, ""} else None,
        "reason": payload.get("reason"),
        "exit_reason": payload.get("exit_reason") or payload.get("reason"),
        "source": str(payload.get("source") or "manual"),
        "created_at": str(payload.get("created_at") or utc_now()),
        "closed_at": payload.get("closed_at"),
    }
    if not _use_sqlite():
        return _db_create_trade_journal_entry(row)
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO trade_journal
                (strategy, signal, symbol, status, entry, stop_loss, target, exit_price, pnl, quantity, reason, exit_reason, source, created_at, closed_at)
            VALUES
                (:strategy, :signal, :symbol, :status, :entry, :stop_loss, :target, :exit_price, :pnl, :quantity, :reason, :exit_reason, :source, :created_at, :closed_at)
            """,
            row,
        )
        row["id"] = cursor.lastrowid
    return row


def list_trade_journal(
    limit: int = 100,
    *,
    strategy: str | None = None,
    status: str | None = None,
    symbol: str | None = None,
    date: str | None = None,
) -> list[dict[str, Any]]:
    init_paper_trade_store()
    if not _use_sqlite():
        return _db_list_trade_journal(limit, strategy=strategy, status=status, symbol=symbol, date=date)
    with _connect() as connection:
        filters = []
        values: list[Any] = []
        if strategy:
            filters.append("LOWER(strategy) = LOWER(?)")
            values.append(strategy)
        if status:
            filters.append("LOWER(status) = LOWER(?)")
            values.append(status)
        if symbol:
            filters.append("UPPER(symbol) = UPPER(?)")
            values.append(symbol)
        if date:
            filters.append("substr(created_at, 1, 10) = ?")
            values.append(date[:10])
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        values.append(max(1, min(int(limit), 500)))
        rows = connection.execute(
            f"SELECT * FROM trade_journal {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            values,
        ).fetchall()
    journal = [dict(row) for row in rows]
    if journal:
        return [_journal_with_timestamp(row) for row in journal]
    if strategy or status or symbol or date:
        return []
    return [
        _journal_with_timestamp(
        {
            "id": trade.get("id"),
            "strategy": trade.get("strategy"),
            "signal": trade.get("side"),
            "symbol": trade.get("symbol"),
            "status": trade.get("status"),
            "entry": trade.get("entry"),
            "entry_price": trade.get("entry"),
            "stop_loss": trade.get("stop_loss"),
            "target": trade.get("target"),
            "exit_price": trade.get("exit_price"),
            "pnl": trade.get("pnl"),
            "quantity": trade.get("quantity"),
            "reason": trade.get("reason"),
            "exit_reason": trade.get("reason"),
            "source": "paper_trade",
            "created_at": trade.get("created_at"),
            "closed_at": trade.get("closed_at"),
        }
        )
        for trade in list_paper_trades(limit)
    ]


def get_trade_journal_entry(entry_id: int) -> dict[str, Any] | None:
    init_paper_trade_store()
    if not _use_sqlite():
        return _db_get_trade_journal_entry(entry_id)
    with _connect() as connection:
        row = connection.execute("SELECT * FROM trade_journal WHERE id = ?", (int(entry_id),)).fetchone()
    return _journal_with_timestamp(dict(row)) if row else None


def update_trade_journal_entry(entry_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    init_paper_trade_store()
    allowed = {"strategy", "signal", "symbol", "status", "entry", "entry_price", "stop_loss", "target", "exit_price", "pnl", "quantity", "reason", "exit_reason", "source", "closed_at"}
    filtered = {key: value for key, value in updates.items() if key in allowed and value is not None}
    if "entry_price" in filtered and "entry" not in filtered:
        filtered["entry"] = filtered.pop("entry_price")
    if not filtered:
        existing = get_trade_journal_entry(entry_id)
        if existing is None:
            raise KeyError(entry_id)
        return existing
    if not _use_sqlite():
        return _db_update_trade_journal_entry(entry_id, filtered)
    assignments = []
    values: list[Any] = []
    for key, value in filtered.items():
        assignments.append(f"{key} = ?")
        if key in {"entry", "stop_loss", "target", "exit_price", "pnl"} and value is not None:
            value = float(value)
        if key == "quantity" and value is not None:
            value = int(value)
        values.append(value)
    values.append(int(entry_id))
    with _connect() as connection:
        cursor = connection.execute(f"UPDATE trade_journal SET {', '.join(assignments)} WHERE id = ?", values)
        if cursor.rowcount == 0:
            raise KeyError(entry_id)
    updated = get_trade_journal_entry(entry_id)
    if updated is None:
        raise KeyError(entry_id)
    return updated


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _init_db_store() -> None:
    from Backend.core import database
    from Backend.core.schema_migrations import apply_compatibility_migrations

    database.init_database()
    apply_compatibility_migrations(database.engine, ("paper_trades", "trade_journal"))


def _paper_trade_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy": str(payload.get("strategy") or payload.get("strategy_name") or "unknown"),
        "symbol": str(payload.get("symbol") or "").upper(),
        "side": str(payload.get("side") or "").upper(),
        "entry": float(payload.get("entry") or payload.get("entry_price") or 0.0),
        "stop_loss": float(payload.get("stop_loss") or 0.0),
        "target": float(payload.get("target") or payload.get("target_price") or 0.0),
        "trailing_stop_loss": _float_or_none(payload.get("trailing_stop_loss")),
        "trailing_stop_pct": _float_or_none(payload.get("trailing_stop_pct")),
        "status": str(payload.get("status") or "paper_simulated"),
        "pnl": float(payload.get("pnl") or 0.0),
        "reason": payload.get("reason"),
        "broker_order_id": payload.get("broker_order_id"),
        "broker_status": payload.get("broker_status"),
        "raw_safe_broker_response": _json_or_none(payload.get("raw_safe_broker_response")),
        "score": float(payload.get("score") or 0.0),
        "regime": payload.get("regime"),
        "signal_time": payload.get("signal_time"),
        "created_at": str(payload.get("created_at") or utc_now()),
    }


def _record_to_dict(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "strategy": record.strategy,
        "symbol": record.symbol,
        "side": record.side,
        "entry": record.entry,
        "stop_loss": record.stop_loss,
        "target": record.target,
        "trailing_stop_loss": record.trailing_stop_loss,
        "trailing_stop_pct": record.trailing_stop_pct,
        "status": record.status,
        "pnl": record.pnl,
        "reason": record.reason,
        "broker_order_id": record.broker_order_id,
        "broker_status": record.broker_status,
        "raw_safe_broker_response": _parse_json_or_none(record.raw_safe_broker_response),
        "score": record.score,
        "regime": record.regime,
        "signal_time": record.signal_time,
        "created_at": record.created_at,
    }


def _db_create_paper_trade(payload: dict[str, Any]) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PaperTradeRecord

    row = _paper_trade_row(payload)
    with SessionLocal() as db:
        record = PaperTradeRecord(**row)
        db.add(record)
        db.commit()
        db.refresh(record)
        row = _record_to_dict(record)
        _record_trade_journal_from_paper_trade(row)
        return row


def _record_trade_journal_from_paper_trade(trade: dict[str, Any]) -> None:
    try:
        create_trade_journal_entry(
            {
                "strategy": trade.get("strategy"),
                "signal": trade.get("side"),
                "symbol": trade.get("symbol"),
                "status": trade.get("status") or "paper_trade",
                "entry": trade.get("entry"),
                "stop_loss": trade.get("stop_loss"),
                "target": trade.get("target"),
                "pnl": trade.get("pnl") or 0.0,
                "quantity": trade.get("quantity"),
                "reason": trade.get("reason"),
                "source": "paper_trade",
                "created_at": trade.get("created_at"),
            }
        )
    except Exception:
        # Journal writes must not break execution paths.
        return


def _db_list_paper_trades(limit: int = 100) -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PaperTradeRecord

    with SessionLocal() as db:
        rows = db.query(PaperTradeRecord).order_by(PaperTradeRecord.created_at.desc(), PaperTradeRecord.id.desc()).limit(max(1, min(int(limit), 500))).all()
        return [_record_to_dict(row) for row in rows]


def _db_update_paper_trade_status(
    broker_order_id: str,
    *,
    status: str,
    reason: str | None = None,
    pnl: float | None = None,
    broker_status: str | None = None,
    raw_safe_broker_response: Any | None = None,
) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import PaperTradeRecord

    with SessionLocal() as db:
        row = (
            db.query(PaperTradeRecord)
            .filter(PaperTradeRecord.broker_order_id == broker_order_id)
            .order_by(PaperTradeRecord.id.desc())
            .first()
        )
        if row is None:
            return None
        row.status = status
        if reason is not None:
            row.reason = reason
        if pnl is not None:
            row.pnl = float(pnl)
        if broker_status is not None:
            row.broker_status = broker_status
        if raw_safe_broker_response is not None:
            row.raw_safe_broker_response = _json_or_none(raw_safe_broker_response)
        db.commit()
        db.refresh(row)
        return _record_to_dict(row)


def _trade_journal_record_to_dict(record: Any) -> dict[str, Any]:
    return _journal_with_timestamp({
        "id": record.id,
        "strategy": record.strategy,
        "signal": record.signal,
        "symbol": record.symbol,
        "status": record.status,
        "entry": record.entry,
        "entry_price": record.entry,
        "stop_loss": record.stop_loss,
        "target": record.target,
        "exit_price": record.exit_price,
        "pnl": record.pnl,
        "quantity": record.quantity,
        "reason": record.reason,
        "exit_reason": record.exit_reason,
        "source": record.source,
        "created_at": record.created_at,
        "closed_at": record.closed_at,
    })


def _db_create_trade_journal_entry(row: dict[str, Any]) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import TradeJournalRecord

    with SessionLocal() as db:
        record = TradeJournalRecord(**row)
        db.add(record)
        db.commit()
        db.refresh(record)
        return _trade_journal_record_to_dict(record)


def _db_list_trade_journal(
    limit: int = 100,
    *,
    strategy: str | None = None,
    status: str | None = None,
    symbol: str | None = None,
    date: str | None = None,
) -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import TradeJournalRecord

    with SessionLocal() as db:
        query = db.query(TradeJournalRecord)
        if strategy:
            query = query.filter(TradeJournalRecord.strategy == strategy)
        if status:
            query = query.filter(TradeJournalRecord.status == status)
        if symbol:
            query = query.filter(TradeJournalRecord.symbol == symbol.upper())
        if date:
            query = query.filter(TradeJournalRecord.created_at.like(f"{date[:10]}%"))
        rows = query.order_by(TradeJournalRecord.created_at.desc(), TradeJournalRecord.id.desc()).limit(max(1, min(int(limit), 500))).all()
        return [_trade_journal_record_to_dict(row) for row in rows]


def _db_get_trade_journal_entry(entry_id: int) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import TradeJournalRecord

    with SessionLocal() as db:
        row = db.get(TradeJournalRecord, int(entry_id))
        return _trade_journal_record_to_dict(row) if row else None


def _db_update_trade_journal_entry(entry_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import TradeJournalRecord

    with SessionLocal() as db:
        row = db.get(TradeJournalRecord, int(entry_id))
        if row is None:
            raise KeyError(entry_id)
        for key, value in updates.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return _trade_journal_record_to_dict(row)


def _journal_with_timestamp(row: dict[str, Any]) -> dict[str, Any]:
    created_at = row.get("created_at")
    entry = row.get("entry")
    return {
        **row,
        "timestamp": row.get("timestamp") or created_at,
        "entry_price": row.get("entry_price", entry),
    }


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _parse_json_or_none(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def risk_status() -> dict[str, Any]:
    init_paper_trade_store()
    from Backend.core.config import get_settings
    from Backend.application.position_store import position_summary

    settings = get_settings()
    positions = position_summary()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    week_start = now - timedelta(days=7)
    trades = list_paper_trades(500)
    today_trades = [trade for trade in trades if str(trade.get("created_at", "")).startswith(today)]
    closed_statuses = {"closed", "exited", "completed"}
    closed_trade_pnl = sum(
        float(trade.get("pnl") or 0.0)
        for trade in today_trades
        if str(trade.get("status") or "").lower() in closed_statuses
    )
    daily_pnl = round(float(positions["todays_pnl"]) + closed_trade_pnl, 2)
    weekly_closed_pnl = sum(
        float(trade.get("pnl") or 0.0)
        for trade in trades
        if str(trade.get("status") or "").lower() in closed_statuses
        and _trade_created_at(trade) is not None
        and _trade_created_at(trade) >= week_start
    )
    weekly_pnl = round(float(positions["unrealized_pnl"]) + weekly_closed_pnl, 2)
    consecutive_losses = 0
    for trade in trades:
        if float(trade.get("pnl") or 0.0) < 0:
            consecutive_losses += 1
        else:
            break

    return {
        "daily_pnl": daily_pnl,
        "weekly_pnl": weekly_pnl,
        "trades_today": len(today_trades),
        "capital": settings.capital,
        "risk_per_trade_pct": settings.risk_per_trade_pct,
        "risk_per_trade_amount": round(settings.capital * settings.risk_per_trade_pct / 100, 2),
        "open_positions": positions["open_positions"],
        "current_exposure": positions["current_exposure"],
        "realized_pnl": positions["realized_pnl"],
        "unrealized_pnl": positions["unrealized_pnl"],
        "consecutive_losses": consecutive_losses,
        "max_daily_loss": settings.max_daily_loss,
        "max_weekly_loss": float(os.getenv("QUANTGRID_MAX_WEEKLY_LOSS", str(settings.max_daily_loss * 3))),
        "max_trades_per_day": int(os.getenv("QUANTGRID_MAX_TRADES_PER_DAY", "3")),
        "max_consecutive_losses": int(os.getenv("QUANTGRID_MAX_CONSECUTIVE_LOSSES", "2")),
        "max_open_positions": int(os.getenv("QUANTGRID_MAX_OPEN_POSITIONS", "3")),
        "max_quantity": int(os.getenv("QUANTGRID_MAX_QUANTITY", "1800")),
        "risk_configured": settings.risk_configured,
    }


def _trade_created_at(trade: dict[str, Any]) -> datetime | None:
    raw = str(trade.get("created_at") or "")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
