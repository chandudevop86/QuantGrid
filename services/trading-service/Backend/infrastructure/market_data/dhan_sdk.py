from __future__ import annotations

from typing import Any

from Backend.infrastructure.broker.dhan_status import dhan_credentials


class DhanSdkUnavailable(RuntimeError):
    pass


def dhan_sdk_client() -> Any:
    credentials = dhan_credentials()
    client_id = credentials["client_id"]
    access_token = credentials["access_token"]
    if not client_id or not access_token:
        raise DhanSdkUnavailable("broker not configured")
    try:
        from dhanhq import DhanContext, dhanhq
    except Exception as exc:
        raise DhanSdkUnavailable("dhanhq package is not installed") from exc
    return dhanhq(DhanContext(client_id, access_token))


def dhan_market_feed_class() -> Any:
    try:
        from dhanhq import DhanContext, MarketFeed
    except Exception as exc:
        raise DhanSdkUnavailable("dhanhq package is not installed") from exc
    credentials = dhan_credentials()
    if not credentials["client_id"] or not credentials["access_token"]:
        raise DhanSdkUnavailable("broker not configured")
    return DhanContext(credentials["client_id"], credentials["access_token"]), MarketFeed
