from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_FILE = Path(os.getenv("MARKET_DATA_DB_FILE", DATA_DIR / "market_data.sqlite3"))
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


def init_market_data_store() -> None:
    global _initialized_store_key

    store_key = _market_data_store_key()
    if _initialized_store_key == store_key:
        return

    with _init_lock:
        store_key = _market_data_store_key()
        if _initialized_store_key == store_key:
            return
        _initialize_market_data_store()
        _initialized_store_key = store_key


def _market_data_store_key() -> tuple[str, object]:
    if _use_sqlite():
        return ("sqlite", str(DB_FILE.resolve()))
    from Backend.core.database import engine

    return ("sqlalchemy", engine)


def _initialize_market_data_store() -> None:
    if not _use_sqlite():
        _init_db_store()
        return
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_price_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                market_symbol TEXT NOT NULL,
                price REAL NOT NULL,
                change_pct REAL,
                source TEXT NOT NULL,
                exchange_timezone TEXT,
                observed_at TEXT NOT NULL,
                stored_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_price_ticks_symbol_observed
            ON market_price_ticks(symbol, observed_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_candles (
                symbol TEXT NOT NULL,
                market_symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER,
                source TEXT NOT NULL,
                exchange_timezone TEXT,
                stored_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (symbol, interval, timestamp)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_candles_symbol_interval_timestamp
            ON market_candles(symbol, interval, timestamp DESC)
            """
        )


def store_price_tick(payload: dict[str, Any]) -> None:
    init_market_data_store()
    if not _use_sqlite():
        _db_store_price_tick(payload)
        return
    symbol = str(payload.get("symbol") or "").upper()
    market_symbol = str(payload.get("market_symbol") or symbol)
    price = payload.get("price")
    if not symbol or price is None:
        return

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO market_price_ticks
                (symbol, market_symbol, price, change_pct, source, exchange_timezone, observed_at, stored_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                market_symbol,
                float(price),
                float(payload["change_pct"]) if payload.get("change_pct") is not None else None,
                str(payload.get("source") or "unknown"),
                payload.get("exchange_timezone"),
                str(payload.get("timestamp") or utc_now()),
                utc_now(),
                json.dumps(payload),
            ),
        )


def latest_price_tick(symbol: str) -> dict[str, Any] | None:
    init_market_data_store()
    if not _use_sqlite():
        return _db_latest_price_tick(symbol)
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT payload_json, stored_at
            FROM market_price_ticks
            WHERE symbol = ?
            ORDER BY observed_at DESC, id DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()

    if row is None:
        return None

    payload = json.loads(row["payload_json"])
    payload["source"] = "stored-live-cache"
    payload["cached_at"] = row["stored_at"]
    return payload


def store_candles(
    *,
    symbol: str,
    market_symbol: str,
    interval: str,
    source: str,
    candles: list[dict[str, Any]],
) -> None:
    init_market_data_store()
    if not _use_sqlite():
        _db_store_candles(symbol=symbol, market_symbol=market_symbol, interval=interval, source=source, candles=candles)
        return
    if not candles:
        return

    rows = []
    stored_at = utc_now()
    for candle in candles:
        rows.append(
            (
                symbol.upper(),
                market_symbol,
                interval,
                str(candle["timestamp"]),
                float(candle["open"]),
                float(candle["high"]),
                float(candle["low"]),
                float(candle["close"]),
                int(candle["volume"]) if candle.get("volume") is not None else None,
                source,
                candle.get("exchange_timezone"),
                stored_at,
                json.dumps(candle),
            )
        )

    with _connect() as connection:
        connection.executemany(
            """
            INSERT INTO market_candles
                (symbol, market_symbol, interval, timestamp, open, high, low, close, volume, source,
                 exchange_timezone, stored_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, timestamp) DO UPDATE SET
                market_symbol = excluded.market_symbol,
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                source = excluded.source,
                exchange_timezone = excluded.exchange_timezone,
                stored_at = excluded.stored_at,
                payload_json = excluded.payload_json
            """,
            rows,
        )


def latest_candles(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    init_market_data_store()
    if not _use_sqlite():
        return _db_latest_candles(symbol, interval, limit)
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM market_candles
            WHERE symbol = ? AND interval = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (symbol.upper(), interval, int(limit)),
        ).fetchall()

    candles = [json.loads(row["payload_json"]) for row in rows]
    candles.reverse()
    return candles


def market_data_summary(symbol: str, interval: str) -> dict[str, Any]:
    init_market_data_store()
    if not _use_sqlite():
        return _db_market_data_summary(symbol, interval)
    with _connect() as connection:
        price_count = connection.execute(
            "SELECT COUNT(*) FROM market_price_ticks WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()[0]
        candle_count = connection.execute(
            "SELECT COUNT(*) FROM market_candles WHERE symbol = ? AND interval = ?",
            (symbol.upper(), interval),
        ).fetchone()[0]
        latest_candle = connection.execute(
            """
            SELECT timestamp, stored_at
            FROM market_candles
            WHERE symbol = ? AND interval = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (symbol.upper(), interval),
        ).fetchone()

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "price_ticks": int(price_count),
        "candles": int(candle_count),
        "latest_candle_at": latest_candle["timestamp"] if latest_candle else None,
        "latest_stored_at": latest_candle["stored_at"] if latest_candle else None,
        "db_file": str(DB_FILE),
    }


def _use_sqlite() -> bool:
    from Backend.application.store_backend import use_legacy_sqlite_store

    return use_legacy_sqlite_store()


def _init_db_store() -> None:
    from Backend.core.database import init_database

    init_database()


def _db_store_price_tick(payload: dict[str, Any]) -> None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import MarketPriceTickRecord

    symbol = str(payload.get("symbol") or "").upper()
    market_symbol = str(payload.get("market_symbol") or symbol)
    price = payload.get("price")
    if not symbol or price is None:
        return
    with SessionLocal() as db:
        db.add(
            MarketPriceTickRecord(
                symbol=symbol,
                market_symbol=market_symbol,
                price=float(price),
                change_pct=float(payload["change_pct"]) if payload.get("change_pct") is not None else None,
                source=str(payload.get("source") or "unknown"),
                exchange_timezone=payload.get("exchange_timezone"),
                observed_at=str(payload.get("timestamp") or utc_now()),
                stored_at=utc_now(),
                payload_json=json.dumps(payload),
            )
        )
        db.commit()


def _db_latest_price_tick(symbol: str) -> dict[str, Any] | None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import MarketPriceTickRecord

    with SessionLocal() as db:
        row = (
            db.query(MarketPriceTickRecord)
            .filter(MarketPriceTickRecord.symbol == symbol.upper())
            .order_by(MarketPriceTickRecord.observed_at.desc(), MarketPriceTickRecord.id.desc())
            .first()
        )
        if row is None:
            return None
        payload = json.loads(row.payload_json)
        payload["source"] = "stored-live-cache"
        payload["cached_at"] = row.stored_at
        return payload


def _db_store_candles(
    *,
    symbol: str,
    market_symbol: str,
    interval: str,
    source: str,
    candles: list[dict[str, Any]],
) -> None:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import MarketCandleRecord

    if not candles:
        return
    stored_at = utc_now()
    with SessionLocal() as db:
        for candle in candles:
            record = MarketCandleRecord(
                symbol=symbol.upper(),
                interval=interval,
                timestamp=str(candle["timestamp"]),
                market_symbol=market_symbol,
                open=float(candle["open"]),
                high=float(candle["high"]),
                low=float(candle["low"]),
                close=float(candle["close"]),
                volume=int(candle["volume"]) if candle.get("volume") is not None else None,
                source=source,
                exchange_timezone=candle.get("exchange_timezone"),
                stored_at=stored_at,
                payload_json=json.dumps(candle),
            )
            db.merge(record)
        db.commit()


def _db_latest_candles(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import MarketCandleRecord

    with SessionLocal() as db:
        rows = (
            db.query(MarketCandleRecord)
            .filter(MarketCandleRecord.symbol == symbol.upper(), MarketCandleRecord.interval == interval)
            .order_by(MarketCandleRecord.timestamp.desc())
            .limit(int(limit))
            .all()
        )
        candles = [json.loads(row.payload_json) for row in rows]
        candles.reverse()
        return candles


def _db_market_data_summary(symbol: str, interval: str) -> dict[str, Any]:
    from sqlalchemy import func
    from Backend.core.database import SessionLocal
    from Backend.domain.trading_store_models import MarketCandleRecord, MarketPriceTickRecord

    with SessionLocal() as db:
        price_count = db.query(func.count(MarketPriceTickRecord.id)).filter(MarketPriceTickRecord.symbol == symbol.upper()).scalar() or 0
        candle_count = (
            db.query(func.count(MarketCandleRecord.timestamp))
            .filter(MarketCandleRecord.symbol == symbol.upper(), MarketCandleRecord.interval == interval)
            .scalar()
            or 0
        )
        latest_candle = (
            db.query(MarketCandleRecord)
            .filter(MarketCandleRecord.symbol == symbol.upper(), MarketCandleRecord.interval == interval)
            .order_by(MarketCandleRecord.timestamp.desc())
            .first()
        )
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "price_ticks": int(price_count),
        "candles": int(candle_count),
        "latest_candle_at": latest_candle.timestamp if latest_candle else None,
        "latest_stored_at": latest_candle.stored_at if latest_candle else None,
        "database": "sqlalchemy",
    }
