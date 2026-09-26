from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class HealthResult:
    name: str
    ok: bool
    status: int | None
    detail: str


Opener = Callable[[urllib.request.Request, float], Any]


def request_json(
    name: str,
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 10.0,
    opener: Opener | None = None,
) -> HealthResult:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    open_request = opener or urllib.request.urlopen

    try:
        with open_request(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            response.read()
            return HealthResult(name=name, ok=200 <= status < 300, status=status, detail="ok")
    except urllib.error.HTTPError as exc:
        return HealthResult(name=name, ok=False, status=exc.code, detail=f"http_{exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return HealthResult(name=name, ok=False, status=None, detail=exc.__class__.__name__)


def summarize(results: list[HealthResult]) -> dict[str, Any]:
    return {
        "healthy": all(item.ok for item in results),
        "checks": [
            {
                "name": item.name,
                "ok": item.ok,
                "status": item.status,
                "detail": item.detail,
            }
            for item in results
        ],
    }
