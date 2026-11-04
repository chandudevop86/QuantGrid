"""PostgreSQL-only reservation foundation; never submits or authorizes orders.

A single row is locked per broker account, serializing exposure decisions across
all application processes sharing the same PostgreSQL primary.
Schema must be provisioned by migrations before calling this module.
"""
from decimal import Decimal, InvalidOperation

from sqlalchemy import text


class PostgresReservationRejected(ValueError):
    pass


def _amount(value):
    if isinstance(value, bool):
        raise PostgresReservationRejected("invalid premium")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PostgresReservationRejected("invalid premium") from exc
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise PostgresReservationRejected("invalid premium")
    return amount


def reserve_postgres_premium(engine, *, broker_account_id, actor_id, key,
                             premium_rupees, cap_rupees=5000):
    """Reserve atomically; rejects missing account provisioning and stale keys.

    Requires a PostgreSQL SQLAlchemy engine. The account row must already exist;
    never create an account based on client input.
    """
    if engine.dialect.name != "postgresql":
        raise PostgresReservationRejected("PostgreSQL required for multi-instance reservation")
    if any(not isinstance(v, str) or not v.strip()
           for v in (broker_account_id, actor_id, key)) or not 16 <= len(key) <= 128:
        raise PostgresReservationRejected("invalid reservation identity")
    premium, cap = _amount(premium_rupees), _amount(cap_rupees)
    if cap > Decimal("5000"):
        raise PostgresReservationRejected("cap cannot exceed 5000")
    with engine.begin() as connection:
        account = connection.execute(text("""
            SELECT broker_account_id FROM option_live_account_locks
            WHERE broker_account_id = :account FOR UPDATE
        """), {"account": broker_account_id}).first()
        if account is None:
            raise PostgresReservationRejected("broker account not provisioned")
        previous = connection.execute(text("""
            SELECT id, premium_rupees, state FROM option_live_pg_reservations
            WHERE broker_account_id=:account AND actor_id=:actor AND idem_key=:key
        """), {"account": broker_account_id, "actor": actor_id, "key": key}).first()
        if previous:
            if Decimal(str(previous.premium_rupees)) != premium:
                raise PostgresReservationRejected("idempotency amount conflict")
            return {"reservation_id": previous.id, "state": previous.state, "replayed": True}
        used = connection.execute(text("""
            SELECT COALESCE(SUM(premium_rupees),0) FROM option_live_pg_reservations
            WHERE broker_account_id=:account AND state <> 'released'
        """), {"account": broker_account_id}).scalar_one()
        if Decimal(str(used)) + premium > cap:
            raise PostgresReservationRejected("live premium cap exceeded")
        row = connection.execute(text("""
            INSERT INTO option_live_pg_reservations
                (broker_account_id,actor_id,idem_key,premium_rupees,state)
            VALUES (:account,:actor,:key,:premium,'reserved')
            RETURNING id
        """), {"account": broker_account_id, "actor": actor_id, "key": key,
                 "premium": premium}).scalar_one()
        return {"reservation_id": row, "state": "reserved", "replayed": False}


def _lock_reservation(connection, *, broker_account_id, actor_id, key):
    row = connection.execute(text("""
        SELECT id,state FROM option_live_pg_reservations
        WHERE broker_account_id=:account AND actor_id=:actor AND idem_key=:key
        FOR UPDATE
    """), {"account": broker_account_id, "actor": actor_id, "key": key}).first()
    if row is None:
        raise PostgresReservationRejected("reservation not found")
    return row


def bind_postgres_broker_order(engine, *, broker_account_id, actor_id, key,
                               broker_order_id, security_id):
    """Immutable order binding; trusted server-side caller only."""
    if engine.dialect.name != "postgresql":
        raise PostgresReservationRejected("PostgreSQL required")
    if any(not isinstance(v, str) or not v.strip() for v in
           (broker_account_id, actor_id, key, broker_order_id, security_id)):
        raise PostgresReservationRejected("invalid identity")
    with engine.begin() as connection:
        row = _lock_reservation(connection, broker_account_id=broker_account_id,
                                actor_id=actor_id, key=key)
        if row.state != "reserved":
            raise PostgresReservationRejected("reservation not in reserved state")
        existing = connection.execute(text("""
            SELECT broker_order_id,security_id FROM option_live_pg_order_bindings
            WHERE reservation_id=:id
        """), {"id": row.id}).first()
        if existing:
            if (existing.broker_order_id, existing.security_id) != (broker_order_id, security_id):
                raise PostgresReservationRejected("immutable order binding conflict")
            return {"reservation_id": row.id, "bound": True, "replayed": True}
        connection.execute(text("""
            INSERT INTO option_live_pg_order_bindings
                (reservation_id,broker_account_id,broker_order_id,security_id)
            VALUES (:id,:account,:order,:security)
        """), {"id": row.id, "account": broker_account_id,
                 "order": broker_order_id, "security": security_id})
        return {"reservation_id": row.id, "bound": True, "replayed": False}


def transition_postgres_reservation(engine, *, broker_account_id, actor_id, key,
                                    expected_state, next_state):
    """Record a trusted server-side submission state without releasing exposure.

    Only reserved -> unknown and unknown -> submitted are allowed here.
    'unknown' MUST be recorded before any external submission attempt; after
    a crash or timeout, reconcile with the broker before any retry. This
    function never submits an order and cannot authorize a second submission.
    """
    if engine.dialect.name != "postgresql":
        raise PostgresReservationRejected("PostgreSQL required")
    if (not isinstance(broker_account_id, str) or not broker_account_id.strip()
            or not isinstance(actor_id, str) or not actor_id.strip()
            or not isinstance(key, str) or not 16 <= len(key) <= 128):
        raise PostgresReservationRejected("invalid reservation identity")
    if (expected_state, next_state) not in (
        ("reserved", "unknown"), ("unknown", "submitted")
    ):
        raise PostgresReservationRejected("forbidden reservation transition")
    with engine.begin() as connection:
        row = _lock_reservation(connection, broker_account_id=broker_account_id,
                                actor_id=actor_id, key=key)
        if row.state != expected_state:
            raise PostgresReservationRejected("reservation state mismatch")
        bound = connection.execute(text("""
            SELECT reservation_id FROM option_live_pg_order_bindings
            WHERE reservation_id=:id AND broker_account_id=:account
        """), {"id": row.id, "account": broker_account_id}).first()
        if bound is None:
            raise PostgresReservationRejected("immutable broker order binding required")
        connection.execute(text("""
            UPDATE option_live_pg_reservations SET state=:next
            WHERE id=:id AND state=:expected
        """), {"id": row.id, "next": next_state, "expected": expected_state})
        return {"reservation_id": row.id, "state": next_state}


def release_postgres_rejected_order(engine, *, broker_account_id, actor_id, key,
                                    broker_order_id, security_id, sdk_client,
                                    configured_client_id=None):
    """Release only after authenticated account identity and broker zero-fill.

    The SDK and configured_client_id MUST come from trusted server-side
    credentials, never from HTTP request parameters or user-provided snapshots.
    Missing identity fails closed; this function never submits broker orders.
    """
    from .dhan_reconciliation_reader import verify_dhan_nonfill
    from .dhan_account_identity import verify_dhan_account_identity

    if engine.dialect.name != "postgresql":
        raise PostgresReservationRejected("PostgreSQL required")
    verified_account = verify_dhan_account_identity(
        sdk_client=sdk_client, configured_client_id=configured_client_id,
    )
    if verified_account != broker_account_id:
        raise PostgresReservationRejected("authenticated broker account mismatch")
    with engine.begin() as connection:
        row = _lock_reservation(connection, broker_account_id=broker_account_id,
                                actor_id=actor_id, key=key)
        if row.state not in ("submitted", "unknown"):
            raise PostgresReservationRejected("reservation not releasable")
        bound = connection.execute(text("""
            SELECT broker_account_id,broker_order_id,security_id
            FROM option_live_pg_order_bindings WHERE reservation_id=:id
        """), {"id": row.id}).first()
        if (bound is None or (bound.broker_account_id, bound.broker_order_id,
                bound.security_id) != (broker_account_id, broker_order_id, security_id)):
            raise PostgresReservationRejected("broker order identity mismatch")
        verified = verify_dhan_nonfill(sdk_client=sdk_client,
                                       order_id=broker_order_id,
                                       security_id=security_id)
        if verified.get("release_eligible") is not True:
            raise PostgresReservationRejected("broker zero-fill not proven")
        updated = connection.execute(text("""
            UPDATE option_live_pg_reservations SET state='released'
            WHERE id=:id AND state IN ('submitted','unknown') RETURNING id
        """), {"id": row.id}).first()
        if updated is None:
            raise PostgresReservationRejected("reservation changed concurrently")
        return {"reservation_id": row.id, "state": "released"}
