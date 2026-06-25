from __future__ import annotations

import json
import os
import base64
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DHAN_PROFILE_URL = "https://api.dhan.co/v2/profile"


def _masked(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def dhan_credentials() -> dict[str, str | None]:
    return {
        "client_id": os.getenv("QUANTGRID_BROKER_CLIENT_ID") or os.getenv("DHAN_CLIENT_ID"),
        "access_token": os.getenv("QUANTGRID_BROKER_ACCESS_TOKEN") or os.getenv("DHAN_ACCESS_TOKEN"),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_status(*, connected: bool, authenticated: bool, error: str | None, message: str, client_id: str | None = None) -> dict[str, Any]:
    return {
        "provider": "dhan",
        "configured": authenticated,
        "connected": connected,
        "authenticated": authenticated,
        "paper_only": True,
        "paper_mode": True,
        "last_checked": _now_iso(),
        "error": error,
        "message": message,
        "client_id": _masked(client_id),
    }


def _jwt_expired(token: str) -> bool:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return False
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = int(decoded.get("exp") or 0)
        return bool(exp and exp <= int(time.time()))
    except Exception:
        return False


def check_dhan_profile(timeout: float = 8.0) -> dict[str, Any]:
    credentials = dhan_credentials()
    client_id = credentials["client_id"]
    access_token = credentials["access_token"]
    if not client_id:
        return _base_status(
            connected=False,
            authenticated=False,
            error="missing_client_id",
            message="Dhan client ID is not configured.",
            client_id=None,
        )
    if not access_token:
        return _base_status(
            connected=False,
            authenticated=False,
            error="token_missing",
            message="Dhan access token is not configured.",
            client_id=client_id,
        )
    if _jwt_expired(access_token):
        return _base_status(
            connected=False,
            authenticated=False,
            error="token_expired",
            message="Dhan access token is expired. Generate a fresh session token.",
            client_id=client_id,
        )

    request = Request(
        DHAN_PROFILE_URL,
        headers={
            "access-token": access_token,
            "Accept": "application/json",
            "User-Agent": "QuantGrid/1.0",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error = "invalid_token" if exc.code in {401, 403} else f"http_{exc.code}"
        return _base_status(
            connected=False,
            authenticated=False,
            error=error,
            message=f"Dhan rejected the configured token with HTTP {exc.code}.",
            client_id=client_id,
        )
    except TimeoutError as exc:
        return _base_status(
            connected=False,
            authenticated=False,
            error="api_timeout",
            message=f"Dhan profile API timed out: {exc}",
            client_id=client_id,
        )
    except (OSError, URLError, ValueError) as exc:
        return _base_status(
            connected=False,
            authenticated=False,
            error="api_unavailable",
            message=f"Could not reach Dhan profile API: {exc}",
            client_id=client_id,
        )

    status = _base_status(
        connected=True,
        authenticated=True,
        error=None,
        message="Dhan credentials are valid. Execution remains paper-only unless live trading is explicitly enabled.",
        client_id=str(payload.get("dhanClientId") or client_id or ""),
    )
    status["account_name"] = payload.get("clientName")
    return status
