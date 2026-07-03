from __future__ import annotations

from app.narratives.fo_narrative_loop import generate_narrative_signal
from tests.test_fo_narrative_loop import _input

from Backend.application.market_copilot import build_market_copilot, reset_market_copilot_state
from conftest import admin_headers


def test_market_copilot_explains_signal_without_blind_call(monkeypatch):
    reset_market_copilot_state()
    expected = generate_narrative_signal(
        _input(
            spot_price=112,
            futures_price=112.3,
            previous_spot=109,
            max_pain=110,
        )
    )
    monkeypatch.setattr("Backend.application.market_copilot.run_fno_narrative", lambda symbol: expected)

    payload = build_market_copilot("NIFTY")

    assert payload["module"] == "market_copilot"
    assert payload["confidence_score"] == expected.confidence
    assert payload["invalidation_text"]
    assert payload["bullish_reasons"]
    assert payload["bearish_reasons"]
    assert "not an order instruction" in payload["summary"].lower()
    assert "blind buy/sell calls" in " ".join(payload["guardrails"]).lower()
    assert not payload["summary"].lower().startswith(("buy ", "sell "))


def test_market_copilot_reports_what_changed(monkeypatch):
    reset_market_copilot_state()
    first = generate_narrative_signal(_input(spot_price=105))
    second = generate_narrative_signal(_input(spot_price=112, previous_spot=109, max_pain=110))
    calls = iter([first, second])
    monkeypatch.setattr("Backend.application.market_copilot.run_fno_narrative", lambda symbol: next(calls))

    first_payload = build_market_copilot("NIFTY")
    second_payload = build_market_copilot("NIFTY")

    assert "First copilot snapshot loaded" in first_payload["what_changed"][0]
    assert any("Spot changed" in item or "Scenario changed" in item for item in second_payload["what_changed"])


def test_market_copilot_api_contract(app_client, monkeypatch):
    from Backend.presentation.api import trading_api

    monkeypatch.setattr(trading_api, "build_market_copilot", lambda symbol: {
        "module": "market_copilot",
        "symbol": symbol,
        "summary": "Wait mode: explanation only, not an order instruction.",
        "signal_explanation": {},
        "bullish_reasons": [],
        "bearish_reasons": [],
        "invalidation_level": None,
        "confidence_score": 50,
        "market_narrative": "ok",
        "what_changed": [],
        "guardrails": ["No blind buy/sell calls."],
    })

    response = app_client.get("/trading/copilot/market?symbol=NIFTY", headers=admin_headers(app_client))

    assert response.status_code == 200, response.text
    assert response.json()["module"] == "market_copilot"
