from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).with_name("quantgrid.sqlite3")
_memory_orders: dict[str, dict[str, Any]] = {}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_order(order_id: str, payload: dict[str, Any], status: str = "queued") -> None:
    try:
        init_db()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO orders (id, payload, status)
                VALUES (?, ?, ?)
                """,
                (order_id, json.dumps(payload), status),
            )
    except sqlite3.Error:
        _memory_orders[order_id] = {
            "id": order_id,
            "payload": payload,
            "status": status,
            "created_at": "memory",
        }


def list_orders() -> list[dict[str, Any]]:
    try:
        init_db()
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT id, payload, status, created_at FROM orders ORDER BY created_at DESC"
            ).fetchall()

        return [
            {
                "id": row["id"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    except sqlite3.Error:
        return list(_memory_orders.values())
