from Backend.application.compliance.retail_algo_release_gate import (
    AlgoReleaseRequest, REQUIRED_CONTROLS, evaluate_algo_release,
)


def request():
    return AlgoReleaseRequest("tenant-a", "broker-a", "algo-a", "v1", "exchange-a", "idem-a")


def test_missing_approvals_never_authorize():
    result = evaluate_algo_release(request(), {})
    assert not result["execution_authorized"]
    assert "broker_hosting_approved" in result["missing"]


def test_all_asserted_approvals_still_do_not_authorize():
    result = evaluate_algo_release(request(), {name: True for name in REQUIRED_CONTROLS})
    assert result["ready_for_review"]
    assert not result["execution_authorized"]


def test_false_and_string_evidence_fail_closed():
    evidence = {name: True for name in REQUIRED_CONTROLS}
    evidence["account_owned_by_tenant"] = "true"
    result = evaluate_algo_release(request(), evidence)
    assert "account_owned_by_tenant" in result["missing"]


def test_missing_tenant_identity_denied():
    r = request()
    invalid = AlgoReleaseRequest("", r.broker_account_id, r.strategy_id,
                                 r.strategy_version, r.exchange_algo_id,
                                 r.order_idempotency_key)
    assert not evaluate_algo_release(invalid, {name: True for name in REQUIRED_CONTROLS})["ready_for_review"]
