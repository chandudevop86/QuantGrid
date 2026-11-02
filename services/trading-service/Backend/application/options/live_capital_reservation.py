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


def transition_live_reservation(db_path, *, actor_id, key, expected_state, next_state,
                                broker_reconciliation_confirmed=False):
    """Compare-and-swap state transition; never calls the broker.

    Unknown broker outcomes remain locked. 'released' requires verified
    reconciliation, even after an apparent rejection.
    """
    transitions = {
        "reserved": {"submitted", "unknown", "released"},
        "submitted": {"unknown", "filled", "released"},
        "unknown": {"filled", "released"},
        "filled": {"released"},
    }
    if (expected_state not in transitions or next_state not in transitions[expected_state]
            or not isinstance(actor_id, str) or not actor_id.strip()
            or not isinstance(key, str) or not 16 <= len(key) <= 128):
        raise ReservationRejected("invalid reservation transition")
    if next_state == "released":
        raise ReservationRejected("direct release forbidden: use reconciled release API")
    path = Path(db_path)
    if not path.is_file():
        raise ReservationRejected("durable reservation database not provisioned")
    with sqlite3.connect(str(path), timeout=30, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT id,state FROM option_live_reservations WHERE actor_id=? AND idem_key=?",
                (actor_id, key)).fetchone()
            if not row or row[1] != expected_state:
                raise ReservationRejected("reservation state mismatch")
            db.execute(
                "UPDATE option_live_reservations SET state=? WHERE id=? AND state=?",
                (next_state, row[0], expected_state))
            db.execute("COMMIT")
            return {"reservation_id": row[0], "state": next_state}
        except BaseException:
            db.execute("ROLLBACK")
            raise


def release_rejected_live_reservation(db_path, *, actor_id, key, sdk_client,
                                      broker_order_id, security_id):
    """Only the trusted server-side Dhan reader can authorize a non-fill release.

    No caller-supplied boolean or broker snapshot can authorize this path.
    This does not handle filled positions or any broker order submission.
    """
    from .dhan_reconciliation_reader import verify_dhan_nonfill

    result = verify_dhan_nonfill(sdk_client=sdk_client, order_id=broker_order_id,
                                 security_id=security_id)
    if result.get("release_eligible") is not True:
        raise ReservationRejected("Dhan reconciliation did not prove zero-fill")
    path = Path(db_path)
    if not path.is_file():
        raise ReservationRejected("durable reservation database not provisioned")
    with sqlite3.connect(str(path), timeout=30, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT id,state FROM option_live_reservations WHERE actor_id=? AND idem_key=?",
                (actor_id, key)).fetchone()
            if not row or row[1] not in ("submitted", "unknown"):
                raise ReservationRejected("reservation state not releasable")
            db.execute(
                "UPDATE option_live_reservations SET state='released' WHERE id=? AND state=?",
                (row[0], row[1]))
            db.execute("COMMIT")
            return {"reservation_id": row[0], "state": "released",
                    "broker_order_id": broker_order_id}
        except BaseException:
            db.execute("ROLLBACK")
            raise
