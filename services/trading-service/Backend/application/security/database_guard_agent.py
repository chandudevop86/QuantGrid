"""Database security and remediation triage: safe, offline policy checks.

No database connections, production mutation, credential retrieval, or auto-merges.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    financial_scope: bool
    production_scope: bool
    tenant_scope: bool
    details: str = ""


SAFE_AUTOFIX = frozenset({
    "format_sql_migration", "update_test_fixture", "add_missing_test",
    "pin_dev_only_dependency", "redact_sample_secret",
})
CRITICAL_CODES = frozenset({
    "sql_injection", "cross_tenant_access", "unencrypted_broker_token",
    "missing_audit_log", "public_database", "missing_database_backup",
    "weak_database_auth", "unrestricted_database_port",
})


def triage_database_finding(finding: Finding) -> dict:
    if not isinstance(finding, Finding):
        return {"decision": "manual_review", "reason": "invalid finding"}
    if finding.severity not in {"low", "medium", "high", "critical"}:
        return {"decision": "manual_review", "reason": "unknown severity"}
    if (finding.code in CRITICAL_CODES or finding.severity in {"high", "critical"}
            or finding.financial_scope or finding.production_scope or finding.tenant_scope):
        return {"decision": "manual_review",
                "reason": "security, client, financial or production impact; urgent triage"}
    if finding.code in SAFE_AUTOFIX:
        return {"decision": "draft_fix_pr_only",
                "reason": "nonfinancial change may be proposed with tests; never auto-merge"}
    return {"decision": "manual_review", "reason": "unclassified change fails closed"}


def evaluate_database_controls(*, tls_required, network_private, least_privilege,
                               tenant_isolation_verified, backups_verified,
                               restore_tested, audit_enabled, encryption_at_rest):
    flags = locals()
    failed = sorted(k for k, v in flags.items() if v is not True)
    return {"secure_baseline_verified": not failed,
            "failed_controls": failed,
            "production_change_allowed": False}
