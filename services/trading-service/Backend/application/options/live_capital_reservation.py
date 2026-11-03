"""Durable, atomic live capital reservations. Never submits broker orders.

Use a provisioned SQLite volume; one reservation per broker idempotency key.
Unknown broker outcomes remain reserved until reconciliation.
"""
import math
import sqlite3
from pathlib import Path


class ReservationRejected(ValueError):
    pass


def reserve_live_premium(db_path, *, actor_id, key, premium_rupees, cap_rupees=5000.0):
    if (not isinstance(actor_id, str) or not actor_id.strip()
            or not isinstance(key, str) or not 16 <= len(key) <= 128):
        raise ReservationRejected("invalid actor or idempotency key")
    if (type(premium_rupees) not in (int, float) or not math.isfinite(premium_rupees)
            or premium_rupees <= 0 or type(cap_rupees) not in (int, float)
            or not math.isfinite(cap_rupees) or not 0 < cap_rupees <= 5000):
        raise ReservationRejected("invalid amount or cap")
    path = Path(db_path)
    if not path.parent.is_dir() or not path.exists():
        raise ReservationRejected("durable reservation database not provisioned")
    with sqlite3.connect(str(path), timeout=30, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS option_live_reservations (
                id INTEGER PRIMARY KEY, actor_id TEXT NOT NULL, idem_key TEXT NOT NULL,
                premium_rupees REAL NOT NULL CHECK(premium_rupees > 0),
                state TEXT NOT NULL CHECK(state IN ('reserved','submitted','unknown','filled','released')),
                UNIQUE(actor_id, idem_key))""")
            previous = db.execute(
                "SELECT id,premium_rupees,state FROM option_live_reservations WHERE actor_id=? AND idem_key=?",
                (actor_id, key)).fetchone()
            if previous:
                if previous[1] != float(premium_rupees):
                    raise ReservationRejected("idempotency key amount conflict")
                result = {"reservation_id": previous[0], "state": previous[2], "replayed": True}
            else:
                # Global cap across actors is conservative for a shared broker account.
                used = db.execute("SELECT COALESCE(SUM(premium_rupees),0) FROM option_live_reservations WHERE state != 'released'").fetchone()[0]
                if used + premium_rupees > cap_rupees:
                    raise ReservationRejected("live premium cap exceeded")
                cursor = db.execute(
                    "INSERT INTO option_live_reservations(actor_id,idem_key,premium_rupees,state) VALUES(?,?,?,'reserved')",
                    (actor_id, key, float(premium_rupees)))
                result = {"reservation_id": cursor.lastrowid, "state": "reserved", "replayed": False}
            db.execute("COMMIT")
            return result
        except BaseException:
            db.execute("ROLLBACK")
            raise
