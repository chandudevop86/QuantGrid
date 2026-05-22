from __future__ import annotations

import json
import os
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


def check_dhan_profile(timeout: float = 8.0) -> dict[str, Any]:
    credentials = dhan_credentials()
    access_token = credentials["access_token"]
    if not access_token:
        return {
            "provider": "dhan",
            "configured": False,
            "connected": False,
            "paper_mode": True,
            "message": "Dhan access token is not configured.",
        }

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
        return {
            "provider": "dhan",
            "configured": True,
            "connected": False,
            "paper_mode": True,
            "client_id": _masked(credentials["client_id"]),
            "message": f"Dhan rejected the configured token with HTTP {exc.code}.",
        }
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        return {
            "provider": "dhan",
            "configured": True,
            "connected": False,
            "paper_mode": True,
            "client_id": _masked(credentials["client_id"]),
            "message": f"Could not reach Dhan profile API: {exc}",
        }

    return {
        "provider": "dhan",
        "configured": True,
        "connected": True,
        "paper_mode": True,
        "client_id": _masked(str(payload.get("dhanClientId") or credentials["client_id"] or "")),
        "account_name": payload.get("clientName"),
        "message": "Dhan credentials are valid. Execution remains paper-only.",
    }
