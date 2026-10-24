"""Fail-closed exchange quote freshness validation for option-buyer research.

A browser refresh time, provider fetch time, or locally generated timestamp
must never be used in place of the exchange's own quote timestamp.
This module does not authorize or submit orders.
"""
from datetime import datetime, timedelta, timezone


class QuoteFreshnessError(ValueError):
    """The exchange quote cannot be established as current."""


def verify_exchange_quote_timestamp(timestamp: str, *, now: datetime | None = None,
                                    max_age_seconds: int = 30) -> datetime:
    """Validate an ISO-8601, timezone-aware exchange quote timestamp.

    Return its UTC instant only when its age is within [0, max_age_seconds].
    Reject missing timezone, future quotes, stale quotes and non-string inputs.
    """
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise QuoteFreshnessError("exchange quote timestamp missing")
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise QuoteFreshnessError("invalid quote freshness policy")
    try:
        parsed = datetime.fromisoformat(timestamp.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise QuoteFreshnessError("invalid exchange quote timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QuoteFreshnessError("exchange quote timezone missing")
    current = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise QuoteFreshnessError("timezone-aware validation clock required")
    quote_utc = parsed.astimezone(timezone.utc)
    age = current.astimezone(timezone.utc) - quote_utc
    if age < timedelta(0):
        raise QuoteFreshnessError("future exchange quote")
    if age > timedelta(seconds=max_age_seconds):
        raise QuoteFreshnessError("stale exchange quote")
    return quote_utc
