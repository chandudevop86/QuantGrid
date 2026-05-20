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
