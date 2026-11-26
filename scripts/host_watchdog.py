"""Read-only host watchdog. Never submits orders, restarts services, or exposes secrets."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time as monotonic_clock
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

SERVICES = ("quantgrid-backend", "quantgrid-worker", "postgresql", "redis-server")
HEALTH_URL = "http://127.0.0.1:8000/health"
IST = timezone(timedelta(hours=5, minutes=30))


def _worker_starting() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "show", "quantgrid-worker", "-p", "ActiveEnterTimestampMonotonic", "--value"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        entered = int(result.stdout.strip()) / 1_000_000
        grace = max(0, float(os.getenv("QUANTGRID_WATCHDOG_STARTUP_GRACE_SECONDS", "90")))
        return result.returncode == 0 and entered > 0 and 0 <= monotonic_clock.monotonic() - entered < grace
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def service_status(name: str) -> dict:
    try:
        p = subprocess.run(["systemctl", "is-active", name], capture_output=True,
                           text=True, timeout=5, check=False)
        return {"name": name, "ok": p.returncode == 0 and p.stdout.strip() == "active"}
    except (OSError, subprocess.TimeoutExpired):
        return {"name": name, "ok": False}


def api_status() -> dict:
    try:
        request = urllib.request.Request(HEALTH_URL, headers={"X-Forwarded-Proto": "https"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
            # Do not expose response contents: health may include credentials or identifiers.
            healthy = (
                response.status == 200
                and isinstance(data, dict)
                and data.get("status") == "ok"
                and isinstance(data.get("services"), dict)
                and bool(data["services"])
                and all(
                    isinstance(service, dict) and service.get("healthy") is True
                    for service in data["services"].values()
                )
            )
            return {"name": "backend_api", "ok": healthy}
    except (OSError, ValueError, urllib.error.URLError):
        return {"name": "backend_api", "ok": False}


def broker_status() -> dict:
    try:
        request = urllib.request.Request(HEALTH_URL + "/broker-readiness",
                                         headers={"X-Forwarded-Proto": "https"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
        ready = response.status == 200 and data.get("ready") is True
        allowed = {"token_expired", "token_missing", "invalid_token", "missing_client_id",
                   "api_timeout", "api_unavailable", "broker_unavailable", "broker_check_failed"}
        reason = data.get("reason")
        return {"name": "dhan_authentication", "ok": ready,
                "reason": "authenticated" if ready else reason if reason in allowed else "broker_unavailable"}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"name": "dhan_authentication", "ok": False, "reason": "broker_check_failed"}


def scanner_status(*, now: datetime | None = None) -> dict:
    clock = (now or datetime.now(timezone.utc)).astimezone(IST)
    path = Path(os.getenv("QUANTGRID_WORKER_PROGRESS_FILE", "/var/lib/quantgrid/worker-progress.json"))
    try:
        progress = json.loads(path.read_text())
        if not isinstance(progress, dict):
            raise ValueError("invalid progress")
    except (OSError, ValueError):
        progress = {}
    holidays = str(progress.get("holidays") or os.getenv("QUANTGRID_NSE_HOLIDAYS", "")).split(",")
    expected = (clock.weekday() < 5 and clock.date().isoformat() not in {item.strip() for item in holidays}
                and time(9, 15) <= clock.time().replace(tzinfo=None) < time(15, 30))
    if not expected:
        return {"name": "auto_paper_scanner", "ok": True, "reason": "outside_market_hours"}
    if not progress and _worker_starting():
        return {"name": "auto_paper_scanner", "ok": True, "reason": "worker_startup_grace"}
    try:
        threshold = max(60.0, float(os.getenv("QUANTGRID_WATCHDOG_SCAN_STALE_SECONDS", "300")))
        timestamps = [progress["last_progress_at"], progress.get("last_scan_completed_at", progress["started_at"])]
        ages = []
        for value in timestamps:
            observed = datetime.fromisoformat(value)
            if observed.tzinfo is None:
                raise ValueError("timezone required")
            ages.append((clock - observed).total_seconds())
    except (KeyError, TypeError, ValueError):
        return {"name": "auto_paper_scanner", "ok": False, "reason": "progress_missing_or_invalid"}
    if not progress.get("auto_paper_enabled"):
        return {"name": "auto_paper_scanner", "ok": False, "reason": "scanner_disabled"}
    if any(age < -5 or age > threshold for age in ages):
        return {"name": "auto_paper_scanner", "ok": False, "reason": "scan_progress_stale"}
    failed = progress.get("last_scan_status") in {"failed", "partial_failure", "degraded"}
    return {"name": "auto_paper_scanner", "ok": not failed,
            "reason": "scan_failed" if failed else "progress_current"}


def notify_status(report: dict) -> dict:
    """Notify configured HTTPS webhook on failure changes and recovery."""
    destination = os.getenv("QUANTGRID_WATCHDOG_WEBHOOK_URL", "").strip()
    if not destination:
        return {"configured": False, "delivered": False}
    try:
        parsed = urllib.parse.urlsplit(destination)
    except ValueError:
        return {"configured": True, "delivered": False, "reason": "invalid_webhook_configuration"}
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return {"configured": True, "delivered": False, "reason": "invalid_webhook_configuration"}
    state_path = Path(os.getenv("QUANTGRID_WATCHDOG_NOTIFICATION_STATE", "/var/lib/quantgrid/watchdog-notification.json"))
    signature = {"healthy": report["healthy"], "failures": [
        {"name": check["name"], "reason": check.get("reason", "unhealthy")}
        for check in report["checks"] if not check["ok"]
    ]}
    try:
        previous = json.loads(state_path.read_text())
    except (OSError, ValueError):
        previous = None
    if previous == signature or previous is None and report["healthy"]:
        return {"configured": True, "delivered": False, "reason": "no_transition"}
    request = urllib.request.Request(destination, method="POST",
                                     data=json.dumps({"service": "QuantGrid", **report}).encode(),
                                     headers={"Content-Type": "application/json"})
    temporary = None
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if not 200 <= response.status < 300:
                raise ValueError("webhook rejected report")
        descriptor, temporary = tempfile.mkstemp(prefix="watchdog-state-", dir=state_path.parent)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(signature, stream, sort_keys=True)
        os.replace(temporary, state_path)
        return {"configured": True, "delivered": True}
    except (OSError, ValueError, urllib.error.URLError):
        return {"configured": True, "delivered": False, "reason": "delivery_failed"}
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def option_recovery_status() -> dict:
    path = Path(os.getenv("QUANTGRID_WORKER_PROGRESS_FILE", "/var/lib/quantgrid/worker-progress.json"))
    try:
        progress = json.loads(path.read_text())
        count = int(progress.get("option_recovery_count", 0))
        return {"name": "option_paper_recovery", "ok": count == 0,
                "reason": "positions_require_review" if count else "no_reported_recovery",
                "positions": count}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"name": "option_paper_recovery", "ok": True, "reason": "progress_not_available"}


def main() -> int:
    checks = [service_status(name) for name in SERVICES] + [api_status(), scanner_status(), option_recovery_status(), broker_status()]
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "healthy": all(x["ok"] for x in checks), "checks": checks,
              "mode": "read_only_no_broker_orders_no_auto_restart"}
    report["notification"] = notify_status(report)
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
