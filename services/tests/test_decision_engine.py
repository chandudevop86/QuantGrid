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
    assert decision.confidence >= 70
    assert decision.data_status == "LIVE"
    assert decision.supporting_factors
    assert decision.score_breakdown
    assert "Confidence" in decision.score_reason
    assert "upside" in decision.simple_explanation


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
    assert "downside" in decision.simple_explanation


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
    assert decision.system_status == "STALE"
    assert decision.data_status == "STALE"
    assert "stale" in decision.simple_explanation.lower()


def test_decision_engine_blocks_low_confidence_mixed_setup():
    decision = DecisionEngine().decide(
        DecisionInputs(
            market_live=True,
            valid_for_execution=True,
            risk_blocked=False,
            feed_delay_seconds=18,
            market_bias="BULLISH",
            market_trend="BEARISH",
            oi_bias="BEARISH",
            pcr=0.8,
            vix=24,
            expiry_day=True,
        )
    )

    assert decision.trade_recommendation == "No Trade"
    assert decision.blocked is True
    assert decision.confidence < 70
    assert decision.data_status == "DEGRADED"
    assert decision.opposing_factors
    assert decision.warnings
    assert any(item["weight"] < 0 for item in decision.score_breakdown)


def test_decision_engine_penalizes_low_liquidity_and_weak_momentum():
    decision = DecisionEngine().decide(
        DecisionInputs(
            market_live=True,
            valid_for_execution=True,
            risk_blocked=False,
            feed_delay_seconds=2,
            market_bias="BULLISH",
            momentum="BEARISH",
            liquidity="LOW",
        )
    )

    assert decision.trade_recommendation == "No Trade"
    assert any("Momentum" in factor for factor in decision.opposing_factors)
    assert any("Liquidity" in warning for warning in decision.warnings)
