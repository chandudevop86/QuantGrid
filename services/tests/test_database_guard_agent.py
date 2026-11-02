from Backend.application.security.database_guard_agent import (
    Finding, triage_database_finding, evaluate_database_controls,
)


def test_nonfinancial_fixture_fix_only_creates_draft():
    x = Finding("update_test_fixture", "low", False, False, False)
    assert triage_database_finding(x)["decision"] == "draft_fix_pr_only"


def test_tenant_isolation_is_never_autofixed():
    x = Finding("cross_tenant_access", "critical", True, True, True)
    assert triage_database_finding(x)["decision"] == "manual_review"


def test_financial_dependency_requires_review():
    x = Finding("pin_dev_only_dependency", "low", True, False, False)
    assert triage_database_finding(x)["decision"] == "manual_review"


def test_database_baseline_fails_closed():
    args = dict(tls_required=True, network_private=True, least_privilege=True,
                tenant_isolation_verified=True, backups_verified=True,
                restore_tested=False, audit_enabled=True, encryption_at_rest=True)
    result = evaluate_database_controls(**args)
    assert not result["secure_baseline_verified"]
    assert "restore_tested" in result["failed_controls"]
    assert not result["production_change_allowed"]
