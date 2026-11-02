"""Fail-closed SEBI/client-readiness decision helper.

This is an internal engineering gate, not a legal determination, SEBI approval,
or a substitute for an appropriately qualified Indian securities lawyer.
"""
from __future__ import annotations

REQUIRED = (
    "legal_entity_reviewed",
    "business_model_classified",
    "regulatory_counsel_signoff",
    "broker_contract_approved",
    "exchange_algo_approval_verified",
    "client_consent_recorded",
    "tenant_isolation_tested",
    "broker_tokens_tenant_scoped",
    "market_data_licence_verified",
    "order_audit_trail_tested",
    "client_risk_limits_tested",
    "incident_response_tested",
    "grievance_process_documented",
    "privacy_notice_reviewed",
)


def assess_client_launch_readiness(evidence, *, requested_mode="live_algo"):
    """Always deny activation; return missing documentary readiness controls.

    All evidence is untrusted until checked against an immutable, authenticated
    approval register by a separate release authority.
    """
    if requested_mode not in ("research", "paper", "live_algo"):
        return {"ready": False, "activation_allowed": False,
                "missing": list(REQUIRED), "reason": "unknown business model"}
    if not isinstance(evidence, dict):
        return {"ready": False, "activation_allowed": False,
                "missing": list(REQUIRED), "reason": "invalid evidence"}
    required = REQUIRED if requested_mode == "live_algo" else (
        "legal_entity_reviewed", "business_model_classified",
        "regulatory_counsel_signoff", "tenant_isolation_tested",
        "market_data_licence_verified", "privacy_notice_reviewed",
    )
    missing = [key for key in required if evidence.get(key) is not True]
    return {"ready": not missing, "activation_allowed": False,
            "missing": missing,
            "reason": ("documentary review complete; independent release approval required"
                       if not missing else "required controls or approvals missing"),
            "mode": requested_mode}
