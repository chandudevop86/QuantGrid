"""Atomic idempotent paper-option ledger. No broker calls."""
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class IdempotencyConflict(ValueError):
    pass


def record_verified_paper_buy(db_path, actor_id, key, verified):
    """Persist a prevalidated paper order, position and audit atomically.

    Caller must verify contract master, market quote and risk independently.
    This function cannot execute live trades.
    """
    if not actor_id or not isinstance(key, str) or not 16 <= len(key) <= 128:
        raise ValueError("invalid identity or idempotency key")
    if verified.get("execution_mode") != "paper" or verified.get("eligible") is not True:
        raise ValueError("paper eligibility required")
    required = ("symbol", "side", "security_id", "expiry", "strike", "lot_size", "lots", "ask")
    if any(verified.get(k) is None for k in required):
        raise ValueError("missing verified contract fields")
    if verified["symbol"] != "NIFTY" or verified["side"] not in ("CE", "PE"):
        raise ValueError("unsupported contract")
    lot_size, lots = verified["lot_size"], verified["lots"]
    if (not str(verified["security_id"]).isdigit()
            or type(lot_size) is not int or type(lots) is not int
            or lot_size <= 0 or not 1 <= lots <= 10
            or not math.isfinite(float(verified["ask"])) or float(verified["ask"]) <= 0):
        raise ValueError("invalid quantities or price")
    payload = {k: verified[k] for k in required}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(path), timeout=30, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS option_paper_orders (
                id INTEGER PRIMARY KEY, actor_id TEXT NOT NULL, idem_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(actor_id, idem_key))""")
            db.execute("""CREATE TABLE IF NOT EXISTS option_paper_positions (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE,
                security_id TEXT NOT NULL, quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL, status TEXT NOT NULL CHECK(status='open'),
                execution_mode TEXT NOT NULL CHECK(execution_mode='paper'))""")
            db.execute("""CREATE TABLE IF NOT EXISTS option_paper_audit (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE,
                actor_id TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL)""")
            row = db.execute("SELECT id,fingerprint FROM option_paper_orders WHERE actor_id=? AND idem_key=?",
                             (actor_id,key)).fetchone()
            if row:
                if row[1] != fingerprint:
                    raise IdempotencyConflict("key already used for another contract")
                order_id, replayed = row[0], True
            else:
                cur = db.execute("INSERT INTO option_paper_orders(actor_id,idem_key,fingerprint,payload,created_at) VALUES(?,?,?,?,?)",
                                 (actor_id,key,fingerprint,json.dumps(payload,sort_keys=True),now))
                order_id, replayed = cur.lastrowid, False
                db.execute("INSERT INTO option_paper_positions(order_id,security_id,quantity,entry_price,status,execution_mode) VALUES(?,?,?,?,'open','paper')",
                           (order_id,str(verified["security_id"]),lot_size*lots,float(verified["ask"])))
                db.execute("INSERT INTO option_paper_audit(order_id,actor_id,event,created_at) VALUES(?,?,?,?)",
                           (order_id,actor_id,"paper_option_buy_recorded",now))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return {"order_id":order_id,"replayed":replayed,"execution_mode":"paper","broker_submitted":False}
