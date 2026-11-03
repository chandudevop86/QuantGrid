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
