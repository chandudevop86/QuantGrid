from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_FILE: Path | str = Path(os.getenv("RECOMMENDATION_DB_FILE", DATA_DIR / "recommendations.sqlite3"))
_MEMORY_CONNECTION: sqlite3.Connection | None = None


@dataclass(frozen=True, slots=True)
class RecommendationMetrics:
    total_recommendations: int
    precision: float
    recall: float
    false_positives: int
    false_negatives: int
    win_rate: float
    profit_factor: float
    expectancy: float
    max_drawdown: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_recommendations": self.total_recommendations,
            "precision": self.precision,
            "recall": self.recall,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    global _MEMORY_CONNECTION
    if str(DB_FILE) == ":memory:":
        if _MEMORY_CONNECTION is None:
            _MEMORY_CONNECTION = sqlite3.connect(":memory:", timeout=30)
            _MEMORY_CONNECTION.row_factory = sqlite3.Row
        return _MEMORY_CONNECTION
    db_file = Path(DB_FILE)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_file, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_recommendation_store() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                market_bias TEXT NOT NULL,
                risk_level TEXT,
                data_status TEXT,
                invalidation_level TEXT,
                payload_json TEXT NOT NULL,
                outcome TEXT,
                pnl REAL DEFAULT 0,
                actual_direction TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def record_recommendation(symbol: str, decision: Any, payload: dict[str, Any] | None = None, decision_id: str | None = None) -> dict[str, Any]:
    row = {
        "decision_id": decision_id or f"REC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "symbol": symbol.upper(),
        "recommendation": str(getattr(decision, "trade_recommendation", "")),
        "confidence": int(getattr(decision, "confidence", 0)),
        "market_bias": str(getattr(decision, "market_bias", "Neutral")),
        "risk_level": str(getattr(decision, "risk_level", "")),
        "data_status": str(getattr(decision, "data_status", "")),
        "invalidation_level": str(getattr(decision, "invalidation_level", "")),
        "payload_json": json.dumps(payload or (decision.to_dict() if hasattr(decision, "to_dict") else {}), sort_keys=True),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    try:
        init_recommendation_store()
        with _connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO recommendations
                (decision_id, symbol, recommendation, confidence, market_bias, risk_level, data_status, invalidation_level, payload_json, created_at, updated_at)
                VALUES (:decision_id, :symbol, :recommendation, :confidence, :market_bias, :risk_level, :data_status, :invalidation_level, :payload_json, :created_at, :updated_at)
                """,
                row,
            )
    except sqlite3.Error as exc:
        row["persistence_error"] = str(exc)
    return row


def record_recommendation_outcome(
    decision_id: str,
    *,
    outcome: str,
    pnl: float = 0.0,
    actual_direction: str | None = None,
) -> dict[str, Any]:
    init_recommendation_store()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE recommendations
            SET outcome = ?, pnl = ?, actual_direction = ?, updated_at = ?
            WHERE decision_id = ?
            """,
            (outcome, float(pnl), actual_direction, utc_now(), decision_id),
        )
        row = connection.execute("SELECT * FROM recommendations WHERE decision_id = ?", (decision_id,)).fetchone()
    return dict(row) if row else {}


def list_recommendations(limit: int = 500) -> list[dict[str, Any]]:
    try:
        init_recommendation_store()
        with _connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recommendations ORDER BY created_at DESC, id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []


def recommendation_metrics(limit: int = 500) -> dict[str, Any]:
    rows = list_recommendations(limit)
    closed = [row for row in rows if row.get("outcome")]
    trade_rows = [row for row in closed if row.get("recommendation") in {"Buy CE", "Buy PE"}]
    wins = [row for row in trade_rows if str(row.get("outcome")).upper() in {"WIN", "TARGET", "PROFIT"} or float(row.get("pnl") or 0) > 0]
    losses = [row for row in trade_rows if str(row.get("outcome")).upper() in {"LOSS", "STOP", "FAILED"} or float(row.get("pnl") or 0) < 0]
    false_positives = len(losses)
    missed = [
        row for row in closed
        if row.get("recommendation") == "No Trade" and str(row.get("actual_direction") or "").upper() in {"BULLISH", "BEARISH"}
    ]
    gross_profit = sum(max(0.0, float(row.get("pnl") or 0.0)) for row in trade_rows)
    gross_loss = abs(sum(min(0.0, float(row.get("pnl") or 0.0)) for row in trade_rows))
    pnls = [float(row.get("pnl") or 0.0) for row in trade_rows]
    metrics = RecommendationMetrics(
        total_recommendations=len(rows),
        precision=round(len(wins) / max(len(trade_rows), 1), 4),
        recall=round(len(wins) / max(len(wins) + len(missed), 1), 4),
        false_positives=false_positives,
        false_negatives=len(missed),
        win_rate=round(len(wins) / max(len(trade_rows), 1), 4),
        profit_factor=round(gross_profit / gross_loss, 4) if gross_loss else round(gross_profit, 4),
        expectancy=round(sum(pnls) / max(len(pnls), 1), 2),
        max_drawdown=_max_drawdown(pnls),
    )
    return metrics.to_dict()


def _max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(abs(max_dd), 2)
