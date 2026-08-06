from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

_LOCK = Lock()
_SENT: dict[str, datetime] = {}
TTL = timedelta(minutes=10)


def _cleanup(now: datetime) -> None:
    expired = [k for k, t in _SENT.items() if now - t > TTL]
    for k in expired:
        _SENT.pop(k, None)


def should_send(key: str) -> bool:
    now = datetime.utcnow()

    with _LOCK:
        _cleanup(now)

        if key in _SENT:
            return False

        _SENT[key] = now
        return True