"""Fail-closed broker reconciliation decision logic; no broker network calls.

Only pass authenticated, freshly fetched broker responses from a trusted
server-side adapter. Never accept client-provided reconciliation evidence.
"""
from datetime import datetime, timezone
from math import isfinite


def can_release_live_reservation(*, expected_order_id, expected_security_id,
                                 broker_order, broker_positions, fetched_at,
                                 now=None, max_age_seconds=15):
    """Release only when broker confirms terminal non-fill and no open position.

    An order that was filled cannot be released using this predicate: it needs
    a separate verified closed-position and balance reconciliation workflow.
    """
    if (not isinstance(expected_order_id, str) or not expected_order_id.strip()
            or not isinstance(expected_security_id, str)
            or not expected_security_id.isdigit()
            or not isinstance(broker_order, dict)
            or not isinstance(broker_positions, list)):
        return False
    try:
        timestamp = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        age = (current - timestamp.astimezone(timezone.utc)).total_seconds()
        if timestamp.tzinfo is None or not 0 <= age <= max_age_seconds:
            return False
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False
    if (str(broker_order.get("order_id")) != expected_order_id
            or str(broker_order.get("security_id")) != expected_security_id
            or broker_order.get("status") not in ("REJECTED", "CANCELLED", "EXPIRED")
            or type(broker_order.get("filled_quantity")) is not int
            or broker_order["filled_quantity"] != 0):
        return False
    for position in broker_positions:
        if not isinstance(position, dict):
            return False
        if str(position.get("security_id")) == expected_security_id:
            qty = position.get("net_quantity")
            if type(qty) is not int or qty != 0:
                return False
    return True
