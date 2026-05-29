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
                open_pnl REAL NOT NULL DEFAULT 0,
                closed_pnl REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_positions_status_updated
            ON positions(status, updated_at DESC)
            """
        )


def create_open_position(payload: dict[str, Any]) -> dict[str, Any]:
    init_position_store()
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
                 open_pnl, closed_pnl, status, opened_at, closed_at, updated_at)
            VALUES
                (:broker_order_id, :symbol, :side, :quantity, :entry_price, :stop_loss, :target, :current_price,
                 :open_pnl, :closed_pnl, :status, :opened_at, :closed_at, :updated_at)
            """,
            row,
        )
        row["id"] = cursor.lastrowid
    return row


def list_open_positions() -> list[dict[str, Any]]:
    init_position_store()
    _refresh_open_positions()
    return _list_positions("open")


def list_closed_positions(limit: int = 100) -> list[dict[str, Any]]:
    init_position_store()
    return _list_positions("closed", limit=limit)


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
