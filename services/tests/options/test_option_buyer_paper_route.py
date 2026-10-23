"""Safety regression: buyer endpoint cannot place orders through unverified provider data."""
from fastapi import HTTPException
from Backend.presentation.api import market_api


class Actor:
    role = "trader"


class Access:
    user = Actor()


def request(**updates):
    data = {"symbol": "NIFTY", "side": "CE", "strike": 22500, "lots": 1,
            "execution_mode": "paper", "idempotency_key": "test-unique-request-0001"}
    data.update(updates)
    return market_api.OptionBuyerPaperRequest(**data)


def test_paper_endpoint_fails_closed(monkeypatch):
    monkeypatch.setattr(market_api, "kill_switch_status", lambda **kwargs: {"active": False})
    try:
        market_api.submit_option_buyer_paper_order(request(), _access=Access())
    except HTTPException as error:
        assert error.status_code == 503
    else:
        raise AssertionError("Unverified order must not execute")


def test_kill_switch_blocks_paper_order(monkeypatch):
    monkeypatch.setattr(market_api, "kill_switch_status", lambda **kwargs: {"active": True})
    try:
        market_api.submit_option_buyer_paper_order(request(), _access=Access())
    except HTTPException as error:
        assert error.status_code == 423
    else:
        raise AssertionError("Kill switch must block")


def test_viewer_role_rejected():
    class Viewer:
        role = "viewer"
    class AccessViewer:
        user = Viewer()
    try:
        market_api.submit_option_buyer_paper_order(request(), _access=AccessViewer())
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("Viewer cannot submit")


def test_non_paper_mode_rejected_at_schema():
    from pydantic import ValidationError
    try:
        request(execution_mode="live")
    except ValidationError:
        return
    raise AssertionError("Live request must be invalid")


def test_unknown_kill_switch_state_blocks(monkeypatch):
    monkeypatch.setattr(market_api, "kill_switch_status", lambda **kwargs: {})
    try:
        market_api.submit_option_buyer_paper_order(request(), _access=Access())
    except HTTPException as error:
        assert error.status_code == 423
    else:
        raise AssertionError("Unknown kill-switch state must block")


def test_kill_switch_read_error_blocks(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("store unavailable")
    monkeypatch.setattr(market_api, "kill_switch_status", fail)
    try:
        market_api.submit_option_buyer_paper_order(request(), _access=Access())
    except HTTPException as error:
        assert error.status_code == 503
    else:
        raise AssertionError("Kill-switch failure must block")
