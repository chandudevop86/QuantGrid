from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


def utc_now():
    return datetime.now(UTC)


def ist_now():
    return datetime.now(IST)


def utc_to_ist(value: datetime):
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(IST)


def ist_iso_now():
    return datetime.now(IST).isoformat()