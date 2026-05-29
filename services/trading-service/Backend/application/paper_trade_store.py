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
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM paper_trades ORDER BY created_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [dict(row) for row in rows]


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
