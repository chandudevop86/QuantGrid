"""Read-only paper ledger reconciliation. No broker connectivity."""
import sqlite3


class PaperLedgerMismatch(RuntimeError):
    pass


def reconcile_paper_ledger(db_path):
    """Verify every simulated order has exactly one position and audit record.

    This is ledger consistency, not reconciliation against a broker or
    actual fills. Any mismatch fails closed.
    """
    with sqlite3.connect(str(db_path), timeout=10) as db:
        db.execute("PRAGMA query_only=ON")
        order_count = db.execute("SELECT COUNT(*) FROM option_paper_orders").fetchone()[0]
        position_count = db.execute("SELECT COUNT(*) FROM option_paper_positions").fetchone()[0]
        audit_count = db.execute("SELECT COUNT(*) FROM option_paper_audit").fetchone()[0]
        orphan_orders = db.execute("""
            SELECT COUNT(*) FROM option_paper_orders o
            LEFT JOIN option_paper_positions p ON p.order_id=o.id
            LEFT JOIN option_paper_audit a ON a.order_id=o.id
            WHERE p.order_id IS NULL OR a.order_id IS NULL
        """).fetchone()[0]
        orphan_positions = db.execute("""
            SELECT COUNT(*) FROM option_paper_positions p
            LEFT JOIN option_paper_orders o ON o.id=p.order_id
            WHERE o.id IS NULL OR p.execution_mode != 'paper'
        """).fetchone()[0]
        orphan_audits = db.execute("""
            SELECT COUNT(*) FROM option_paper_audit a
            LEFT JOIN option_paper_orders o ON o.id=a.order_id
            WHERE o.id IS NULL
        """).fetchone()[0]
    result = {"orders": order_count, "positions": position_count,
              "audits": audit_count, "orphan_orders": orphan_orders,
              "orphan_positions": orphan_positions, "orphan_audits": orphan_audits}
    if (order_count != position_count or order_count != audit_count
            or orphan_orders or orphan_positions or orphan_audits):
        raise PaperLedgerMismatch(f"paper ledger reconciliation failed: {result}")
    return {"status": "consistent", **result}
