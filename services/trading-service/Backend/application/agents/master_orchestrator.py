"""QuantGrid master-agent approval policy: fail closed, no order execution.

The coordinator produces decisions only. It cannot grant its own approvals,
merge PRs, send orders, or mutate production infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    AUTO = "auto_allowed"
    REVIEW = "manual_approval_required"
    DENY = "prohibited"


@dataclass(frozen=True)
class ChangeRequest:
    agent: str
    action: str
    environment: str
    affects_real_money: bool = False
    affects_clients: bool = False
    affects_broker: bool = False
    affects_regulatory_controls: bool = False
    destructive: bool = False


AUTO_ACTIONS = frozenset({
    "run_unit_tests", "run_static_analysis", "generate_readonly_report",
    "scan_dependencies", "create_draft_pr", "collect_health_metrics",
})
MANUAL_ACTIONS = frozenset({
    "merge_pr", "deploy_production", "modify_risk_limits",
    "change_broker_credentials", "enable_live_trading", "change_client_access",
    "modify_regulatory_policy", "modify_network_firewall",
    "change_trading_strategy", "publish_client_recommendations",
})
DENIED_ACTIONS = frozenset({
    "place_live_order", "withdraw_funds", "disable_audit_logs",
    "bypass_risk_gate", "bypass_security_checks", "share_client_secrets",
})


def classify_change(change: ChangeRequest) -> dict:
    if not isinstance(change, ChangeRequest):
        return {"decision": Decision.DENY.value, "reason": "invalid change request"}
    if (not change.agent or not change.action or
            change.environment not in ("local", "ci", "staging", "production")):
        return {"decision": Decision.DENY.value, "reason": "invalid agent/action/environment"}
    if change.action in DENIED_ACTIONS:
        return {"decision": Decision.DENY.value, "reason": "prohibited action"}
    if (change.action in MANUAL_ACTIONS or change.environment == "production"
            or change.affects_real_money or change.affects_clients
            or change.affects_broker or change.affects_regulatory_controls
            or change.destructive):
        return {"decision": Decision.REVIEW.value,
                "reason": "owner approval and independent execution gates required"}
    if change.action in AUTO_ACTIONS:
        return {"decision": Decision.AUTO.value,
                "reason": "non-production, read-only or draft-only action"}
    return {"decision": Decision.REVIEW.value, "reason": "unclassified action fails closed"}


def approval_notice(*, request_id: str, change: ChangeRequest,
                    reason: str, impact: str, rollback: str) -> str:
    if not request_id or not isinstance(change, ChangeRequest):
        raise ValueError("valid request required")
    decision = classify_change(change)
    return (
        f"QuantGrid approval request {request_id}\\n"
        f"Agent: {change.agent}\\nAction: {change.action}\\n"
        f"Environment: {change.environment}\\n"
        f"Decision: {decision['decision']}\\n"
        f"Reason: {reason}\\nImpact: {impact}\\nRollback: {rollback}\\n"
        "Choices: APPROVE / REJECT / REQUEST CHANGES.\\n"
        "No response = no approval. Approval does not bypass CI, Security, "
        "broker, regulatory or execution controls."
    )
