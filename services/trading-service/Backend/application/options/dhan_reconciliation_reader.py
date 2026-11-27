"""Read-only Dhan SDK reconciliation adapter.

Caller supplies an authenticated server-side SDK client; never accept client
snapshots. This module never places, modifies or cancels orders.
"""
from datetime import datetime, timezone

from .live_broker_reconciliation import can_release_live_reservation


class BrokerReconciliationUnavailable(RuntimeError):
    pass


def _rows(response):
    if not isinstance(response, dict) or str(response.get("status", "")).lower() not in ("success", "successful"):
        raise BrokerReconciliationUnavailable("broker response not successful")
    rows = response.get("data")
    if not isinstance(rows, list):
        raise BrokerReconciliationUnavailable("broker data unavailable")
    return rows


def verify_dhan_nonfill(*, sdk_client, order_id, security_id, now=None):
    """Read broker order book and positions, returning a conservative decision.

    Both broker reads must succeed. Missing order IDs, unknown fields, or
    partially filled orders never authorize release.
    """
    if (not isinstance(order_id, str) or not order_id.strip()
            or not isinstance(security_id, str) or not security_id.isdigit()):
        raise BrokerReconciliationUnavailable("invalid broker identifiers")
    try:
        orders = _rows(sdk_client.get_order_list())
        positions = _rows(sdk_client.get_positions())
    except Exception as exc:
        raise BrokerReconciliationUnavailable("broker order/position fetch failed") from exc
    matching = [o for o in orders if isinstance(o, dict) and str(o.get("orderId")) == order_id]
    if len(matching) != 1:
        raise BrokerReconciliationUnavailable("broker order missing or ambiguous")
    order = matching[0]
    try:
        filled = order.get("filledQty")
        if type(filled) is not int:
            raise ValueError("filled quantity not verified")
        normalized_order = {
            "order_id": str(order["orderId"]),
            "security_id": str(order["securityId"]),
            "status": str(order["orderStatus"]).upper(),
            "filled_quantity": filled,
        }
        normalized_positions = []
        for position in positions:
            if not isinstance(position, dict):
                raise ValueError("invalid position")
            qty = position.get("netQty")
            if type(qty) is not int:
                raise ValueError("position quantity not verified")
            normalized_positions.append({
                "security_id": str(position["securityId"]), "net_quantity": qty,
            })
    except (KeyError, TypeError, ValueError) as exc:
        raise BrokerReconciliationUnavailable("broker schema unverified") from exc
    fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "release_eligible": can_release_live_reservation(
            expected_order_id=order_id, expected_security_id=security_id,
            broker_order=normalized_order, broker_positions=normalized_positions,
            fetched_at=fetched_at, now=now,
        ),
        "order_status": normalized_order["status"],
        "filled_quantity": normalized_order["filled_quantity"],
        "fetched_at": fetched_at,
        "broker_order_submitted": False,
    }
