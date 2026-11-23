"""Atomic idempotent paper-option ledger. No broker calls."""
import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from Backend.application.options.quote_freshness import verify_exchange_quote_timestamp


class IdempotencyConflict(ValueError):
    pass


def ledger_path():
    return Path(os.getenv("QUANTGRID_OPTION_PAPER_LEDGER", Path(__file__).resolve().parents[2] / "data" / "option_paper.sqlite3"))


def _initialize_lifecycle(db):
    # Sidecar tables preserve ledgers created with CHECK(status='open').
    db.execute("""CREATE TABLE IF NOT EXISTS option_paper_exits (
        order_id INTEGER PRIMARY KEY REFERENCES option_paper_orders(id),
        exit_price REAL NOT NULL, pnl REAL NOT NULL, reason TEXT NOT NULL,
        closed_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS option_paper_marks (
        order_id INTEGER PRIMARY KEY REFERENCES option_paper_orders(id),
        price REAL NOT NULL, quote_timestamp TEXT NOT NULL)""")


def list_option_positions(db_path=None):
    path = Path(db_path or ledger_path())
    if not path.is_file():
        return []
    with sqlite3.connect(str(path), timeout=30) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='option_paper_orders'").fetchone():
            return []
        _initialize_lifecycle(db)
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT o.id,o.actor_id,o.idem_key,o.payload,o.created_at,
                p.quantity,p.entry_price,e.exit_price,e.pnl,e.reason,e.closed_at,
                m.price AS mark_price,m.quote_timestamp
            FROM option_paper_orders o JOIN option_paper_positions p ON p.order_id=o.id
            LEFT JOIN option_paper_exits e ON e.order_id=o.id
            LEFT JOIN option_paper_marks m ON m.order_id=o.id
            ORDER BY o.id DESC
        """).fetchall()
    result = []
    for row in rows:
        payload = json.loads(row["payload"])
        price = row["exit_price"] if row["closed_at"] else row["mark_price"]
        pnl = row["pnl"] if row["closed_at"] else ((price - row["entry_price"]) * row["quantity"] if price is not None else None)
        result.append({**payload, "id": row["id"], "actor_id": row["actor_id"], "idempotency_key": row["idem_key"],
                       "symbol": f"NIFTY {payload['expiry']} {float(payload['strike']):g} {payload['side']}",
                       "underlying": "NIFTY", "option_type": payload["side"], "side": "BUY",
                       "quantity": row["quantity"], "entry_price": row["entry_price"],
                       "current_price": price, "quote_timestamp": row["quote_timestamp"],
                       "exit_price": row["exit_price"], "status": "closed" if row["closed_at"] else "open",
                       "pnl": pnl, "closed_pnl": row["pnl"], "open_pnl": pnl if not row["closed_at"] else 0,
                       "opened_at": row["created_at"], "created_at": row["created_at"], "closed_at": row["closed_at"],
                       "exit_reason": row["reason"], "execution_mode": "paper", "product": "OPTIDX paper"})
    return result


def mark_option_position(db_path, order_id, price, quote_timestamp):
    if not math.isfinite(price) or price <= 0:
        raise ValueError("invalid option mark")
    with sqlite3.connect(str(db_path), timeout=30) as db:
        _initialize_lifecycle(db)
        db.execute("INSERT OR REPLACE INTO option_paper_marks(order_id,price,quote_timestamp) VALUES(?,?,?)",
                   (order_id, price, quote_timestamp))


def close_option_position(db_path, order_id, price, reason):
    if not math.isfinite(price) or price <= 0:
        raise ValueError("invalid option exit price")
    with sqlite3.connect(str(db_path), timeout=30, isolation_level=None) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _initialize_lifecycle(db)
            position = db.execute("SELECT quantity,entry_price FROM option_paper_positions WHERE order_id=?", (order_id,)).fetchone()
            if position is None:
                raise ValueError("option paper position not found")
            pnl = round((price - position[1]) * position[0], 2)
            db.execute("INSERT OR IGNORE INTO option_paper_exits(order_id,exit_price,pnl,reason,closed_at) VALUES(?,?,?,?,?)",
                       (order_id, price, pnl, reason, datetime.now(timezone.utc).isoformat()))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return next(row for row in list_option_positions(db_path) if row["id"] == order_id)


def _check_account_limits(db, limits, now):
    # The caller supplies the existing non-option account snapshot. Option
    # counters are read again under BEGIN IMMEDIATE to serialize scanner races.
    open_count = db.execute("""SELECT COUNT(*) FROM option_paper_positions p
        WHERE NOT EXISTS (SELECT 1 FROM option_paper_exits e WHERE e.order_id=p.order_id)""").fetchone()[0]
    clock = datetime.fromisoformat(now)
    ist = timezone(timedelta(hours=5, minutes=30))
    day_start = clock.astimezone(ist).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    week_start = (clock - timedelta(days=7)).isoformat()
    today_count = db.execute("SELECT COUNT(*) FROM option_paper_orders WHERE created_at>=?", (day_start,)).fetchone()[0]
    daily_pnl = db.execute("SELECT COALESCE(SUM(pnl),0) FROM option_paper_exits WHERE closed_at>=?", (day_start,)).fetchone()[0]
    weekly_pnl = db.execute("SELECT COALESCE(SUM(pnl),0) FROM option_paper_exits WHERE closed_at>=?", (week_start,)).fetchone()[0]
    unrealized = db.execute("""SELECT COALESCE(SUM((m.price-p.entry_price)*p.quantity),0)
        FROM option_paper_positions p JOIN option_paper_marks m ON m.order_id=p.order_id
        WHERE NOT EXISTS (SELECT 1 FROM option_paper_exits e WHERE e.order_id=p.order_id)""").fetchone()[0]
    if open_count + int(limits["open_positions"]) >= int(limits["max_open_positions"]):
        raise ValueError("MAX_OPEN_POSITIONS_EXCEEDED")
    if today_count + int(limits["trades_today"]) >= int(limits["max_trades_per_day"]):
        raise ValueError("MAX_TRADES_PER_DAY_EXCEEDED")
    if daily_pnl + unrealized + float(limits["daily_pnl"]) <= -float(limits["max_daily_loss"]):
        raise ValueError("MAX_DAILY_LOSS_EXCEEDED")
    if weekly_pnl + unrealized + float(limits["weekly_pnl"]) <= -float(limits["max_weekly_loss"]):
        raise ValueError("MAX_WEEKLY_LOSS_EXCEEDED")
    outcomes = [(datetime.fromisoformat(timestamp), pnl)
                for timestamp, pnl in db.execute("SELECT closed_at,pnl FROM option_paper_exits")]
    outcomes.extend((datetime.fromisoformat(row["closed_at"]), row["pnl"])
                    for row in limits.get("closed_outcomes", []))
    losses = 0
    for _timestamp, pnl in sorted(outcomes, reverse=True):
        if pnl >= 0:
            break
        losses += 1
    # Legacy ledgers without closure timestamps retain their existing account
    # guard. Do not add independent streaks across a winning reset.
    legacy_losses = int(limits["consecutive_losses"]) if "closed_outcomes" not in limits else 0
    if max(losses, legacy_losses) >= int(limits["max_consecutive_losses"]):
        raise ValueError("MAX_CONSECUTIVE_LOSSES_EXCEEDED")


def record_verified_paper_buy(db_path, actor_id, key, verified, *, max_open_premium_rupees=100000, limits=None):
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
            or type(verified["ask"]) not in (int, float)
            or not math.isfinite(verified["ask"]) or verified["ask"] <= 0):
        raise ValueError("invalid quantities or price")
    if (type(max_open_premium_rupees) not in (int, float)
            or not math.isfinite(max_open_premium_rupees) or max_open_premium_rupees <= 0):
        raise ValueError("invalid paper premium limit")
    payload = {k: verified[k] for k in required}
    for name in ("strategy", "signal_time", "stop_loss", "target", "quote_timestamp", "quote_source", "bid"):
        if name in verified:
            payload[name] = verified[name]
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    path = Path(db_path)
    # The configured storage directory must already exist. Do not silently
    # create a new ledger on an unexpected filesystem or ephemeral mount.
    if not path.parent.is_dir():
        raise FileNotFoundError("paper ledger directory is not provisioned")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(path), timeout=30, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS option_paper_orders (
                id INTEGER PRIMARY KEY, actor_id TEXT NOT NULL, idem_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(actor_id, idem_key))""")
            db.execute("""CREATE TABLE IF NOT EXISTS option_paper_positions (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES option_paper_orders(id),
                security_id TEXT NOT NULL, quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL, status TEXT NOT NULL CHECK(status='open'),
                execution_mode TEXT NOT NULL CHECK(execution_mode='paper'))""")
            db.execute("""CREATE TABLE IF NOT EXISTS option_paper_audit (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES option_paper_orders(id),
                actor_id TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL)""")
            _initialize_lifecycle(db)
            if "quote_timestamp" in verified:
                verify_exchange_quote_timestamp(verified["quote_timestamp"], now=datetime.now(timezone.utc))
            row = db.execute("SELECT id,fingerprint FROM option_paper_orders WHERE actor_id=? AND idem_key=?",
                             (actor_id,key)).fetchone()
            if row:
                if row[1] != fingerprint:
                    raise IdempotencyConflict("key already used for another contract")
                order_id, replayed = row[0], True
                position = db.execute("SELECT quantity,entry_price,security_id,execution_mode FROM option_paper_positions WHERE order_id=?", (order_id,)).fetchone()
                audit = db.execute("SELECT actor_id,event FROM option_paper_audit WHERE order_id=?", (order_id,)).fetchone()
                if (position is None or audit is None
                        or position != (lot_size * lots, float(verified["ask"]), str(verified["security_id"]), "paper")
                        or audit != (actor_id, "paper_option_buy_recorded")):
                    raise RuntimeError("paper ledger replay integrity check failed")
            else:
                # BEGIN IMMEDIATE serializes writers: the cap check and order
                # insert must occur in the same transaction, including across
                # workers sharing this ledger file.
                open_premium = db.execute("""
                    SELECT COALESCE(SUM(p.quantity * p.entry_price), 0)
                    FROM option_paper_positions p
                    JOIN option_paper_orders o ON o.id = p.order_id
                    WHERE (? IS NULL OR o.actor_id = ?) AND p.status = 'open'
                    AND NOT EXISTS (SELECT 1 FROM option_paper_exits e WHERE e.order_id=o.id)
                """, (None if limits is not None else actor_id, actor_id)).fetchone()[0]
                proposed = lot_size * lots * verified["ask"]
                if (not math.isfinite(open_premium) or open_premium < 0
                        or not math.isfinite(proposed)
                        or open_premium + proposed > max_open_premium_rupees):
                    raise ValueError("paper premium exposure limit exceeded")
                if limits is not None:
                    _check_account_limits(db, limits, now)
                cur = db.execute("INSERT INTO option_paper_orders(actor_id,idem_key,fingerprint,payload,created_at) VALUES(?,?,?,?,?)",
                                 (actor_id,key,fingerprint,json.dumps(payload,sort_keys=True),now))
                order_id, replayed = cur.lastrowid, False
                db.execute("INSERT INTO option_paper_positions(order_id,security_id,quantity,entry_price,status,execution_mode) VALUES(?,?,?,?,'open','paper')",
                           (order_id,str(verified["security_id"]),lot_size*lots,float(verified["ask"])))
                db.execute("INSERT INTO option_paper_audit(order_id,actor_id,event,created_at) VALUES(?,?,?,?)",
                           (order_id,actor_id,"paper_option_buy_recorded",now))
            if not replayed and "bid" in verified:
                db.execute("INSERT INTO option_paper_marks(order_id,price,quote_timestamp) VALUES(?,?,?)",
                           (order_id, verified["bid"], verified["quote_timestamp"]))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return {"order_id":order_id,"replayed":replayed,"execution_mode":"paper","broker_submitted":False}
