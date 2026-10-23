"""Safety checks for NIFTY Option Buyer live-market observations."""
from datetime import datetime, timezone
from math import isfinite


def verify_quote_freshness(timestamp, *, max_age_seconds=30, now=None):
    """Fail closed when exchange/provider quote timestamp is absent or stale."""
    if not isinstance(timestamp, str) or not timestamp.strip():
        return False
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return False
        current = now or datetime.now(timezone.utc)
        age = (current - value.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= max_age_seconds
    except (TypeError, ValueError, OverflowError):
        return False


def verify_lot_size(*, contract_lot_size, exchange_lot_size):
    """A broker option-chain leg is not an authoritative contract master."""
    if type(contract_lot_size) is not int or type(exchange_lot_size) is not int:
        return False
    return contract_lot_size > 0 and contract_lot_size == exchange_lot_size


def verify_premium_exposure(*, ask, lot_size, lots, existing, pending, limit):
    """Pure preflight; caller must atomically reserve capital before any order."""
    values = (ask, existing, pending, limit)
    if (type(lot_size) is not int or type(lots) is not int
            or lot_size <= 0 or lots <= 0
            or not all(isfinite(float(x)) and float(x) >= 0 for x in values)
            or ask <= 0 or limit <= 0):
        return False
    return ask * lot_size * lots + existing + pending <= limit
