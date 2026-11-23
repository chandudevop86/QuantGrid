"""Durable, non-sensitive worker and automatic-scan progress for host monitoring."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
_state: dict = {}


def record_worker_progress(phase: str, *, scan_status: str | None = None,
                           option_recovery_count: int | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    _state.setdefault("started_at", now)
    _state.update(last_progress_at=now, phase=phase,
                  auto_paper_enabled=os.getenv("QUANTGRID_AUTO_PAPER_ENABLED", "").strip().lower() in {"1", "true", "yes"},
                  holidays=os.getenv("QUANTGRID_NSE_HOLIDAYS", ""))
    if scan_status == "started":
        _state["last_scan_started_at"] = now
    elif scan_status is not None:
        _state.update(last_scan_completed_at=now, last_scan_status=scan_status)
    if option_recovery_count is not None:
        _state.update(option_recovery_count=option_recovery_count, option_monitor_checked_at=now)
    path = Path(os.getenv("QUANTGRID_WORKER_PROGRESS_FILE", "/var/lib/quantgrid/worker-progress.json"))
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix="worker-progress-", dir=path.parent)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(_state, stream, sort_keys=True)
        os.replace(temporary, path)
    except OSError:
        logger.warning("worker_progress_write_failed")
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
