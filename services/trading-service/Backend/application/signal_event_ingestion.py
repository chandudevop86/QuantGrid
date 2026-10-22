"""Optional durable scanner audit ingestion; never places or authorizes orders."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from Backend.application.dto import serialize_signal
from Backend.application.signal_evaluation_id import signal_evaluation_id
from Backend.application.signal_event_store import record_signal_evaluation_event
from Backend.core.database import SessionLocal


def scanner_event_ingestion_enabled() -> bool:
    return os.getenv("QUANTGRID_SIGNAL_EVENT_INGESTION", "").strip().lower() in {"1", "true", "yes"}


def record_scanner_decisions(
    accepted: list[Any],
    rejected: list[dict[str, Any]],
    stale: list[dict[str, Any]],
    *,
    snapshot_time: Any,
) -> int:
    """Persist one event per evaluated signal. Raises on DB failure; caller must fail closed."""
    entries: list[tuple[Any, dict[str, Any]]] = (
        [(signal, dict(signal.metadata)) for signal in accepted]
        + [(item["signal"], item["decision"]) for item in rejected]
        + [(item["signal"], item["decision"]) for item in stale]
    )
    if not entries:
        return 0
    count = 0
    with SessionLocal.begin() as session:
        for signal, decision in entries:
            payload = serialize_signal(signal)
            status = str(decision.get("status") or "").upper()
            if status not in {"ACTIVE", "REJECTED", "STALE"}:
                raise ValueError("Missing or invalid terminal signal decision")
            fingerprint = {
                "strategy": signal.strategy_name,
                "symbol": signal.symbol,
                "side": signal.side,
                "signal_time": signal.signal_time.isoformat(),
                "entry": signal.entry_price,
                "stop": signal.stop_loss,
                "target": signal.target_price,
            }
            signal_id = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()[:24]
            record_signal_evaluation_event(session, {
                "evaluation_id": signal_evaluation_id(payload, decision, snapshot_time),
                "event_type": {"ACTIVE": "SIGNAL_ACCEPTED", "REJECTED": "SIGNAL_REJECTED", "STALE": "SIGNAL_STALE"}[status],
                "signal_id": signal_id,
                "strategy": signal.strategy_name,
                "symbol": signal.symbol,
                "side": signal.side,
                "signal_time": signal.signal_time.isoformat(),
                "snapshot_time": str(snapshot_time),
                "status": status,
                "reason": str(decision.get("reason") or "UNKNOWN"),
                "mtf_bias": str(decision.get("mtf_bias") or "UNKNOWN"),
                "evidence": {**decision, "evaluation_source": "live_analysis_worker"},
            })
            count += 1
    return count
