-- Apply via a reviewed database migration before use. No live execution is enabled.
-- Accounts are provisioned by trusted server-side administration only.
CREATE TABLE IF NOT EXISTS option_live_account_locks (
    broker_account_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS option_live_pg_reservations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    broker_account_id TEXT NOT NULL REFERENCES option_live_account_locks(broker_account_id),
    actor_id TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    premium_rupees NUMERIC(14,2) NOT NULL CHECK (premium_rupees > 0),
    state TEXT NOT NULL CHECK (state IN ('reserved','submitted','unknown','filled','released')),
    UNIQUE (broker_account_id, actor_id, idem_key)
);
CREATE INDEX IF NOT EXISTS option_live_pg_active_account_idx
ON option_live_pg_reservations (broker_account_id, state);

CREATE TABLE IF NOT EXISTS option_live_pg_order_bindings (
    reservation_id BIGINT PRIMARY KEY REFERENCES option_live_pg_reservations(id),
    broker_account_id TEXT NOT NULL REFERENCES option_live_account_locks(broker_account_id),
    broker_order_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    UNIQUE (broker_account_id, broker_order_id)
);
