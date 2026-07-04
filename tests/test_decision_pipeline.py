from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

import Backend.application.recommendation_store as recommendation_store
from Backend.application.decision_pipeline import DecisionPipelineService, MarketDataInputs
from Backend.application.recommendation_store import record_recommendation_outcome, recommendation_metrics


def test_decision_pipeline_maps_candles_to_buy_ce_and_persists_metrics(monkeypatch):
    monkeypatch.setattr(recommendation_store, "DB_FILE", ":memory:")
    monkeypatch.setattr(recommendation_store, "_MEMORY_CONNECTION", None)
    result = DecisionPipelineService().run(
        MarketDataInputs(
            symbol="NIFTY",
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=[
                {"close": 100, "vwap": 99},
                {"close": 102, "vwap": 100},
                {"close": 105, "vwap": 101},
                {"close": 108, "vwap": 102},
            ],
            oi_bias="BULLISH",
            fii_dii_bias="BULLISH",
            pcr=1.1,
        ),
        risk_blocked=False,
    )

    assert result.decision.trade_recommendation == "Buy CE"
    assert result.factors["trend"] == "BULLISH"
    assert result.factors["vwap_relation"] == "above VWAP"
    assert result.decision_id

    record_recommendation_outcome(result.decision_id, outcome="WIN", pnl=500, actual_direction="BULLISH")
    metrics = recommendation_metrics()

    assert metrics["total_recommendations"] == 1
    assert metrics["precision"] == 1
    assert metrics["false_positives"] == 0


def test_decision_pipeline_prefers_no_trade_when_votes_conflict(monkeypatch):
    monkeypatch.setattr(recommendation_store, "DB_FILE", ":memory:")
    monkeypatch.setattr(recommendation_store, "_MEMORY_CONNECTION", None)
    result = DecisionPipelineService().run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            trend="BULLISH",
            momentum="BEARISH",
            oi_bias="BULLISH",
            gift_nifty_bias="BEARISH",
        ),
        risk_blocked=False,
    )

    assert result.decision.trade_recommendation == "No Trade"
    assert result.factors["market_bias"] == "NEUTRAL"
