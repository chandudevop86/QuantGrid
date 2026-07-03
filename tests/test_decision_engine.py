from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application.decision_engine import DecisionEngine, DecisionInputs


def test_decision_engine_maps_bullish_bias_to_buy_ce():
    decision = DecisionEngine().decide(
        DecisionInputs(
            market_live=True,
            valid_for_execution=True,
            risk_blocked=False,
            feed_delay_seconds=2,
            market_bias="BULLISH",
        )
    )

    assert decision.market_bias == "Bullish"
    assert decision.trade_recommendation == "Buy CE"
    assert decision.confidence == 78
    assert "bulls" in decision.simple_explanation


def test_decision_engine_maps_bearish_bias_to_buy_pe():
    decision = DecisionEngine().decide(
        DecisionInputs(
            market_live=True,
            valid_for_execution=True,
            risk_blocked=False,
            feed_delay_seconds=2,
            market_bias="BEARISH",
        )
    )

    assert decision.market_bias == "Bearish"
    assert decision.trade_recommendation == "Buy PE"
    assert "bears" in decision.simple_explanation


def test_decision_engine_blocks_when_market_data_is_not_valid():
    decision = DecisionEngine().decide(
        DecisionInputs(
            market_live=True,
            valid_for_execution=False,
            risk_blocked=False,
            warnings=["Latest candle is stale."],
            market_bias="BULLISH",
        )
    )

    assert decision.market_bias == "Neutral"
    assert decision.trade_recommendation == "No Trade"
    assert decision.system_status == "Caution"
    assert "stale" in decision.simple_explanation.lower()
