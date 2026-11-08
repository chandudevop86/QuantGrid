"""Read-only host watchdog. Never submits orders, restarts services, or exposes secrets."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

SERVICES = ("quantgrid-backend", "quantgrid-worker", "postgresql", "redis-server")
HEALTH_URL = "http://127.0.0.1:8000/health"


def service_status(name: str) -> dict:
    try:
        p = subprocess.run(["systemctl", "is-active", name], capture_output=True,
                           text=True, timeout=5, check=False)
        return {"name": name, "ok": p.returncode == 0 and p.stdout.strip() == "active"}
    except (OSError, subprocess.TimeoutExpired):
        return {"name": name, "ok": False}


def api_status() -> dict:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
            data = json.load(response)
            # Do not expose response contents: health may include credentials or identifiers.
            return {"name": "backend_api", "ok": response.status == 200 and isinstance(data, dict)}
    except (OSError, ValueError, urllib.error.URLError):
        return {"name": "backend_api", "ok": False}


def main() -> int:
    checks = [service_status(name) for name in SERVICES] + [api_status()]
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "healthy": all(x["ok"] for x in checks), "checks": checks,
              "mode": "read_only_no_broker_orders_no_auto_restart"}
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
