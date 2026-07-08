from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from Backend.application.notifications import send_alert
from Backend.application.paper_trade_store import DATA_DIR
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is POSIX-only
    fcntl = None  # type: ignore[assignment]


STATUS_FILE = Path(DATA_DIR) / "broker_circuit_breaker.json"
LOCK_FILE = STATUS_FILE.with_suffix(".lock")
DEFAULT_WINDOW_SECONDS = 120
DEFAULT_THRESHOLD = 5
DEFAULT_COOLDOWN_SECONDS = 300


@contextlib.contextmanager
def _state_lock() -> Iterator[None]:
    """Serialize read-modify-write access to the circuit breaker state file.

    Without this, concurrent broker failures -- exactly the scenario this module exists to
    detect -- can race: two requests both read the same failure list, each appends its own
    entry, and whichever writes last wins, silently dropping the other failure and delaying
    (or preventing) circuit-breaker activation right when it matters most. Uses a plain
    POSIX advisory lock (fcntl) rather than a new dependency; falls back to no locking on
    platforms without fcntl (e.g. Windows dev machines), which is a degradation, not a crash.
    """
    if fcntl is None:
        yield
        return
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def broker_circuit_status(*, now: datetime | None = None) -> dict[str, Any]:
    current = now or _utc_now()
    config = _config()
    with _state_lock():
        state = _load_state()
        failures = _recent_failures(state.get("failures", []), current, config["window_seconds"])
        active = _is_active(state, current)
        if state.get("active") and not active:
            state["active"] = False
            state["deactivated_at"] = current.isoformat()
            state["failures"] = failures
            _save_state(state)

    return {
        "active": active,
        "reason": state.get("reason") if active else None,
        "failure_count": len(failures),
        "failure_threshold": config["threshold"],
        "window_seconds": config["window_seconds"],
        "cooldown_seconds": config["cooldown_seconds"],
        "activated_at": state.get("activated_at") if active else None,
        "cooldown_until": state.get("cooldown_until") if active else None,
        "last_failure_at": failures[-1].get("at") if failures else None,
        "updated_at": state.get("updated_at"),
    }


def broker_circuit_active() -> bool:
    return bool(broker_circuit_status().get("active"))


def record_broker_failure(
    *,
    reason: str,
    db: Session | None = None,
    actor: User | None = None,
    request: Request | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _utc_now()
    config = _config()
    activated = False
    with _state_lock():
        state = _load_state()
        failures = _recent_failures(state.get("failures", []), current, config["window_seconds"])
        failures.append({"at": current.isoformat(), "reason": str(reason)})
        state["failures"] = failures
        state["updated_at"] = current.isoformat()

        if len(failures) >= config["threshold"] and not _is_active(state, current):
            activated = True
            state["active"] = True
            state["reason"] = f"Broker failure threshold reached: {len(failures)} failures in {config['window_seconds']}s."
            state["activated_at"] = current.isoformat()
            state["cooldown_until"] = (current + timedelta(seconds=config["cooldown_seconds"])).isoformat()

        _save_state(state)

    if activated:
        _notify_activation(state)
    status = broker_circuit_status(now=current)
    if db is not None:
        write_audit_log(
            db,
            action="broker_circuit_breaker_activated" if activated else "broker_failure_recorded",
            actor=actor,
            target_type="broker",
            target_id="live",
            request=request,
            metadata={
                "status": "activated" if activated else "recorded",
                "reason": state.get("reason") if activated else reason,
                "failure_count": status["failure_count"],
                "failure_threshold": status["failure_threshold"],
                "circuit_breaker": status,
                **(metadata or {}),
            },
        )
    return status


def reset_broker_circuit(*, actor: str | None = None) -> dict[str, Any]:
    current = _utc_now()
    state = {
        "active": False,
        "reason": None,
        "failures": [],
        "activated_at": None,
        "cooldown_until": None,
        "deactivated_at": current.isoformat(),
        "deactivated_by": actor,
        "updated_at": current.isoformat(),
    }
    with _state_lock():
        _save_state(state)
    return broker_circuit_status(now=current)


def _config() -> dict[str, int]:
    return {
        "window_seconds": _int_env("BROKER_FAILURE_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS),
        "threshold": _int_env("BROKER_FAILURE_THRESHOLD", DEFAULT_THRESHOLD),
        "cooldown_seconds": _int_env("BROKER_CIRCUIT_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS),
    }


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _load_state() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return _empty_state()
    try:
        parsed = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    return parsed if isinstance(parsed, dict) else _empty_state()


def _save_state(state: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file in the same directory and atomically rename over the target, so a
    # crash/kill mid-write can't leave behind a truncated/corrupt JSON file that _load_state
    # would then have to silently discard (masking whatever state we were about to record).
    fd, tmp_path = tempfile.mkstemp(dir=str(STATUS_FILE.parent), prefix=".tmp-circuit-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, indent=2, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, STATUS_FILE)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


def _empty_state() -> dict[str, Any]:
    return {
        "active": False,
        "reason": None,
        "failures": [],
        "activated_at": None,
        "cooldown_until": None,
        "deactivated_at": None,
        "deactivated_by": None,
        "updated_at": None,
    }


def _recent_failures(failures: list[dict[str, Any]], now: datetime, window_seconds: int) -> list[dict[str, Any]]:
    cutoff = now - timedelta(seconds=window_seconds)
    recent = []
    for failure in failures:
        occurred_at = _parse_dt(failure.get("at"))
        if occurred_at and occurred_at >= cutoff:
            recent.append({"at": occurred_at.isoformat(), "reason": str(failure.get("reason") or "broker_failure")})
    return recent


def _is_active(state: dict[str, Any], now: datetime) -> bool:
    if not state.get("active"):
        return False
    cooldown_until = _parse_dt(state.get("cooldown_until"))
    return cooldown_until is None or cooldown_until > now


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _notify_activation(state: dict[str, Any]) -> None:
    send_alert(
        "QuantGrid broker circuit breaker active",
        "\n".join(
            [
                "QuantGrid broker circuit breaker active",
                f"Reason: {state.get('reason')}",
                f"Cooldown until: {state.get('cooldown_until')}",
                "Live order placement is blocked. Paper orders remain available.",
            ]
        ),
    )
