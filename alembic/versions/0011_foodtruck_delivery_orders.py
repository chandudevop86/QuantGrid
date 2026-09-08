"""Add KS Foods customer and delivery fields to orders.

Revision ID: 0011_foodtruck_delivery_orders
Revises: 0010_research_scored_at
"""

from alembic import op

revision = "0011_foodtruck_delivery_orders"
down_revision = "0010_research_scored_at"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS phone TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type VARCHAR(20) NOT NULL DEFAULT 'LIVE'")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_address JSONB")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_fee NUMERIC(12,2) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status VARCHAR(30) NOT NULL DEFAULT 'PAID'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_orders_phone_order_number ON orders(phone, order_number)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_orders_phone_order_number")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS payment_status")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS delivery_fee")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS delivery_address")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS order_type")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS phone")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS customer_name")
