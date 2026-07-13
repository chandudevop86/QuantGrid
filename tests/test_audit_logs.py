from __future__ import annotations

from conftest import admin_headers


def test_audit_logs_login_and_user_creation(app_client):
    headers = admin_headers(app_client)
    response = app_client.post(
        "/admin/users/create",
        json={"username": "audited", "password": "AuditPass1!", "role": "analyst"},
        headers=headers,
    )
    assert response.status_code == 200

    from Backend.core.database import SessionLocal
    from Backend.domain.security.models import AuditLog

    with SessionLocal() as db:
        actions = [row.action for row in db.query(AuditLog).all()]

    assert "login_success" in actions
    assert "user_created" in actions


def test_audit_log_sanitizes_nested_secrets(app_client):
    import json

    from Backend.core.database import SessionLocal
    from Backend.domain.security.audit import write_audit_log
    from Backend.domain.security.models import AuditLog

    metadata = {"result": {"access_token": "secret", "nested": [{"password": "hidden"}]}}
    with SessionLocal() as db:
        write_audit_log(db, action="secret_test", metadata=metadata)
        row = db.query(AuditLog).filter(AuditLog.action == "secret_test").one()

    assert metadata["result"]["access_token"] == "secret"
    stored = json.loads(row.metadata_json)
    assert stored["result"]["access_token"] == "[redacted]"
    assert stored["result"]["nested"][0]["password"] == "[redacted]"


def test_audit_schema_columns_have_central_migration_ownership():
    from Backend.core.schema_migrations import COMPATIBILITY_COLUMNS, _statement_for_dialect

    additions = COMPATIBILITY_COLUMNS["audit_logs"]

    assert set(additions) == {"actor_role", "status", "request_id", "reason"}
    assert all(statement.startswith("ALTER TABLE audit_logs ADD COLUMN") for statement in additions.values())
    assert all(
        "ADD COLUMN IF NOT EXISTS" in _statement_for_dialect(statement, "postgresql")
        for statement in additions.values()
    )
    assert all(
        "IF NOT EXISTS" not in _statement_for_dialect(statement, "sqlite")
        for statement in additions.values()
    )
