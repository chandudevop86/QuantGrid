from Backend.application.agents.master_orchestrator import (
    ChangeRequest, classify_change, approval_notice,
)


def test_readonly_ci_action_auto_allowed():
    assert classify_change(ChangeRequest("security", "run_static_analysis", "ci"))["decision"] == "auto_allowed"


def test_live_trading_never_auto_approved():
    assert classify_change(ChangeRequest("financial", "enable_live_trading", "production"))["decision"] == "manual_approval_required"


def test_unclassified_action_requires_approval():
    assert classify_change(ChangeRequest("market", "unknown_change", "ci"))["decision"] == "manual_approval_required"


def test_prohibited_live_order_stays_denied():
    assert classify_change(ChangeRequest("market", "place_live_order", "production"))["decision"] == "prohibited"


def test_approval_notice_includes_options_and_rollback():
    notice = approval_notice(request_id="QG-123",
        change=ChangeRequest("network", "deploy_production", "production"),
        reason="High latency", impact="Short restart", rollback="Revert release")
    assert "APPROVE / REJECT / REQUEST CHANGES" in notice
    assert "Revert release" in notice
