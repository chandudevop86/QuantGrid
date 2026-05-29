from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_FILE = Path(os.getenv("PAPER_TRADE_DB_FILE", DATA_DIR / "paper_trades.sqlite3"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_paper_trade_store() -> None:
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
                status TEXT NOT NULL,
                pnl REAL NOT NULL DEFAULT 0,
                reason TEXT,
                broker_order_id TEXT,
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
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(paper_trades)").fetchall()
        }
        if "broker_order_id" not in columns:
            connection.execute("ALTER TABLE paper_trades ADD COLUMN broker_order_id TEXT")


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
        "status": str(payload.get("status") or "paper_simulated"),
        "pnl": float(payload.get("pnl") or 0.0),
        "reason": payload.get("reason"),
        "broker_order_id": payload.get("broker_order_id"),
        "score": float(payload.get("score") or 0.0),
        "regime": payload.get("regime"),
        "signal_time": payload.get("signal_time"),
        "created_at": created_at,
    }
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO paper_trades
                (strategy, symbol, side, entry, stop_loss, target, status, pnl, reason, broker_order_id, score, regime, signal_time, created_at)
            VALUES
                (:strategy, :symbol, :side, :entry, :stop_loss, :target, :status, :pnl, :reason, :broker_order_id, :score, :regime, :signal_time, :created_at)
            """,
            row,
        )
        row["id"] = cursor.lastrowid
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
) -> dict[str, Any] | None:
    init_paper_trade_store()
    if not _use_sqlite():
        return _db_update_paper_trade_status(broker_order_id, status=status, reason=reason, pnl=pnl)
    updates = ["status = ?"]
    values: list[Any] = [status]
    if reason is not None:
        updates.append("reason = ?")
        values.append(reason)
    if pnl is not None:
        updates.append("pnl = ?")
        values.append(float(pnl))
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


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _init_db_store() -> None:
    from Backend.core.database import Base, engine
    import Backend.domain.trading_store_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _paper_trade_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy": str(payload.get("strategy") or payload.get("strategy_name") or "unknown"),
        "symbol": str(payload.get("symbol") or "").upper(),
        "side": str(payload.get("side") or "").upper(),
        "entry": float(payload.get("entry") or payload.get("entry_price") or 0.0),
        "stop_loss": float(payload.get("stop_loss") or 0.0),
        "target": float(payload.get("target") or payload.get("target_price") or 0.0),
        "status": str(payload.get("status") or "paper_simulated"),
        "pnl": float(payload.get("pnl") or 0.0),
        "reason": payload.get("reason"),
        "broker_order_id": payload.get("broker_order_id"),
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
        "status": record.status,
        "pnl": record.pnl,
        "reason": record.reason,
        "broker_order_id": record.broker_order_id,
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
        row["id"] = record.id
    return row


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
        db.commit()
        db.refresh(row)
        return _record_to_dict(row)


def risk_status() -> dict[str, Any]:
    init_paper_trade_store()
    from Backend.core.config import get_settings
    from Backend.application.position_store import position_summary

    settings = get_settings()
    positions = position_summary()
    today = datetime.now(timezone.utc).date().isoformat()
    trades = list_paper_trades(500)
    today_trades = [trade for trade in trades if str(trade.get("created_at", "")).startswith(today)]
    daily_pnl = round(float(positions["todays_pnl"]), 2)
    consecutive_losses = 0
    for trade in trades:
        if float(trade.get("pnl") or 0.0) < 0:
            consecutive_losses += 1
        else:
            break

    return {
        "daily_pnl": daily_pnl,
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
        "max_trades_per_day": int(os.getenv("QUANTGRID_MAX_TRADES_PER_DAY", "3")),
        "max_consecutive_losses": int(os.getenv("QUANTGRID_MAX_CONSECUTIVE_LOSSES", "2")),
        "max_open_positions": int(os.getenv("QUANTGRID_MAX_OPEN_POSITIONS", "3")),
        "max_quantity": int(os.getenv("QUANTGRID_MAX_QUANTITY", "1800")),
        "risk_configured": settings.risk_configured,
    }
