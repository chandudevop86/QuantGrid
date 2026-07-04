from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

import Backend.application.recommendation_store as recommendation_store
from Backend.application.decision_pipeline import (
    DecisionPipelineService,
    MarketDataInputs,
    analyze_ema,
    analyze_risk_reward,
    analyze_support_resistance,
    analyze_trend,
    analyze_volume,
)
from Backend.application.recommendation_store import record_recommendation_outcome, recommendation_metrics


def _bullish_candles() -> list[dict]:
    candles = []
    for index in range(55):
        close = 100 + index * 0.4
        candles.append({"open": close - 0.4, "high": close + 1.2, "low": close - 1.8, "close": close, "volume": 1000 + index, "vwap": close - 0.8})
    candles[-2] = {"open": 120, "high": 124, "low": 118, "close": 121, "volume": 1200, "vwap": 120}
    candles[-1] = {"open": 122, "high": 130, "low": 122, "close": 125, "volume": 3000, "vwap": 123}
    return candles


def _bearish_candles() -> list[dict]:
    candles = []
    for index in range(55):
        close = 130 - index * 0.45
        candles.append({"open": close + 0.4, "high": close + 1.7, "low": close - 1.0, "close": close, "volume": 1000 + index})
    candles[-2] = {"open": 101, "high": 104, "low": 96, "close": 99, "volume": 1200}
    candles[-1] = {"open": 96, "high": 93, "low": 80, "close": 90, "volume": 3000}
    return candles


def _sideways_candles() -> list[dict]:
    return [
        {"open": 100, "high": 102 + (index % 2), "low": 98 - (index % 2), "close": 100, "volume": 1000}
        for index in range(55)
    ]


def test_decision_pipeline_maps_candles_to_buy_ce_and_persists_metrics(monkeypatch):
    monkeypatch.setattr(recommendation_store, "DB_FILE", ":memory:")
    monkeypatch.setattr(recommendation_store, "_MEMORY_CONNECTION", None)
    result = DecisionPipelineService().run(
        MarketDataInputs(
            symbol="NIFTY",
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_bullish_candles(),
            oi_bias="BULLISH",
            fii_dii_bias="BULLISH",
            pcr=1.1,
        ),
        risk_blocked=False,
    )

    assert result.decision.trade_recommendation == "Buy CE"
    assert result.factors["trend"] == "BULLISH"
    assert result.factors["vwap_relation"] == "above VWAP"
    checklist = result.factors["checklist"]
    assert set(checklist) == {
        "checklist_score",
        "passed",
        "failed",
        "warnings",
        "trend",
        "ema",
        "volume",
        "support_resistance",
        "risk_reward",
    }
    assert checklist["checklist_score"] > 0
    assert checklist["passed"]
    assert checklist["failed"] == []
    assert checklist["trend"]["trend_direction"] == "UPTREND"
    assert checklist["ema"]["ema_bias"] == "BULLISH"
    assert checklist["volume"]["supports_trade"] is True
    assert checklist["risk_reward"]["allowed"] is True
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


def test_trend_analyzer_detects_uptrend_downtrend_and_sideways():
    assert analyze_trend(_bullish_candles()).trend_direction == "UPTREND"
    assert analyze_trend(_bearish_candles()).trend_direction == "DOWNTREND"
    sideways = analyze_trend(_sideways_candles())
    assert sideways.trend_direction == "SIDEWAYS"
    assert sideways.warning_if_sideways


def test_ema_analyzer_bullish_bearish_and_weak():
    assert analyze_ema(_bullish_candles()).ema_bias == "BULLISH"
    assert analyze_ema(_bearish_candles()).ema_bias == "BEARISH"
    weak = analyze_ema(_sideways_candles())
    assert weak.ema_bias == "NEUTRAL"
    assert weak.warning


def test_volume_analyzer_confirms_breakout_and_rejects_low_volume():
    assert analyze_volume(_bullish_candles()).supports_trade is True
    low_volume = _bullish_candles()
    low_volume[-1]["volume"] = 10
    rejected = analyze_volume(low_volume)
    assert rejected.supports_trade is False
    assert rejected.volume_status == "LOW_VOLUME_MOVE"


def test_support_resistance_and_risk_reward_are_calculated():
    candles = _bullish_candles()
    sr = analyze_support_resistance(candles)
    rr = analyze_risk_reward(MarketDataInputs(candles=candles, risk_per_trade=1500, lot_size=50), "BULLISH", sr)

    assert sr.support is not None
    assert sr.resistance is not None
    assert sr.entry_zone
    assert sr.invalidation_level
    assert rr.risk_reward_ratio >= 1.5
    assert rr.allowed is True
    assert rr.position_size >= 50


def test_decision_pipeline_buy_ce_buy_pe_and_blocks_poor_rr(monkeypatch):
    monkeypatch.setattr(recommendation_store, "DB_FILE", ":memory:")
    monkeypatch.setattr(recommendation_store, "_MEMORY_CONNECTION", None)
    bullish = DecisionPipelineService().run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_bullish_candles(),
            oi_bias="BULLISH",
            pcr=1.1,
        ),
        risk_blocked=False,
        persist=False,
    )
    bearish = DecisionPipelineService().run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_bearish_candles(),
            oi_bias="BEARISH",
            pcr=0.8,
        ),
        risk_blocked=False,
        persist=False,
    )
    poor_rr = _bullish_candles()
    poor_rr[-1] = {"open": 128, "high": 130, "low": 127, "close": 129, "volume": 3000}
    blocked = DecisionPipelineService().run(
        MarketDataInputs(market_live=True, valid_for_execution=True, feed_delay_seconds=2, candles=poor_rr),
        risk_blocked=False,
        persist=False,
    )

    assert bullish.decision.trade_recommendation == "Buy CE"
    assert bearish.decision.trade_recommendation == "Buy PE"
    assert blocked.decision.trade_recommendation == "No Trade"
    assert "risk reward is poor" in blocked.factors["checklist_blockers"] or blocked.factors["support_resistance"]["warning"]


def test_decision_pipeline_blocks_stale_data():
    result = DecisionPipelineService().run(
        MarketDataInputs(market_live=True, valid_for_execution=False, feed_delay_seconds=180, candles=_bullish_candles()),
        risk_blocked=False,
        persist=False,
    )

    assert result.decision.trade_recommendation == "No Trade"
    assert "data is stale" in result.factors["checklist_blockers"]
    assert "data is stale" in result.factors["checklist"]["failed"]
