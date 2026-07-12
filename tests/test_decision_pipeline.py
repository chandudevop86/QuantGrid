from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

import Backend.application.recommendation_store as recommendation_store
from Backend.application.decision_pipeline import (
    DecisionPipelineService,
    MarketDataInputs,
    analyze_fvg,
    assess_trade_data_quality,
    analyze_higher_timeframe,
    analyze_liquidity,
    analyze_market_regime,
    analyze_market_structure,
    analyze_price_action,
    analyze_ema,
    analyze_risk_reward,
    analyze_supply_demand,
    analyze_support_resistance,
    analyze_trend,
    analyze_volume,
)
from Backend.application.recommendation_store import record_recommendation_outcome, recommendation_metrics
from Backend.domain.engine.strategy_engine import StrategyEngine


def _bullish_candles() -> list[dict]:
    candles = []
    for index in range(55):
        close = 100 + index * 0.4
        candles.append({"open": close - 0.4, "high": close + 1.2, "low": close - 1.8, "close": close, "volume": 1000 + index, "vwap": close - 0.8})
    candles[-2] = {"open": 124, "high": 125, "low": 118, "close": 121, "volume": 1200, "vwap": 120}
    candles[-1] = {"open": 120, "high": 140, "low": 119, "close": 126, "volume": 3000, "vwap": 123}
    return candles


def _bearish_candles() -> list[dict]:
    candles = []
    for index in range(55):
        close = 130 - index * 0.45
        candles.append({"open": close + 0.4, "high": close + 1.7, "low": close - 1.0, "close": close, "volume": 1000 + index})
    candles[-2] = {"open": 101, "high": 102, "low": 88, "close": 92, "volume": 1200}
    candles[-1] = {"open": 93, "high": 94, "low": 60, "close": 86, "volume": 3000}
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
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
            candles_15m=_bullish_candles(),
            candles_1h=_bullish_candles(),
            oi_bias="BULLISH",
            fii_dii_bias="BULLISH",
            pcr=1.1,
            put_oi=1200,
            call_oi=900,
            fii_cash=100,
            dii_cash=50,
            gift_nifty_bias="BULLISH",
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
        "htf",
        "market_structure",
        "key_levels",
        "supply_demand",
        "fvg",
        "liquidity",
        "price_action",
        "market_regime",
        "strategy_selection",
        "options_flow",
        "institutional",
        "discipline",
        "confluence_engine",
        "confidence_engine",
        "data_quality",
    }
    assert checklist["checklist_score"] > 0
    assert checklist["passed"]
    assert checklist["failed"] == []
    assert checklist["trend"]["trend_direction"] == "UPTREND"
    assert checklist["ema"]["ema_bias"] == "BULLISH"
    assert checklist["volume"]["supports_trade"] is True
    assert checklist["volume"]["smart_money_score"] >= 50
    assert "volume_profile" in checklist["volume"]["details"]
    assert checklist["risk_reward"]["allowed"] is True
    assert checklist["htf"]["passed"] is True
    assert checklist["market_structure"]["latest_structure_event"] in {"BOS", "HH_HL"}
    assert 0 <= checklist["market_structure"]["structure_score"] <= 100
    assert checklist["price_action"]["confirmed"] is True
    assert checklist["options_flow"]["passed"] is True
    assert checklist["institutional"]["passed"] is True
    assert result.factors["high_probability_trade_engine"]["paper_trade_allowed"] is True
    assert result.factors["high_probability_trade_engine"]["paper_trade_gate"]["allowed"] is True
    final_decision = result.factors["final_decision"]
    assert set(final_decision) == {
        "market_bias",
        "trade_decision",
        "selected_strategy",
        "strategy_version",
        "strategy",
        "trade_quality",
        "confidence_score",
        "probability_score",
        "confidence_label",
        "confluence_score",
        "entry_zone",
        "stop_loss",
        "target",
        "risk_reward_ratio",
        "position_size",
        "risk_level",
        "explanation",
        "supporting_factors",
        "opposing_factors",
        "strategy_selection",
        "probability_engine",
        "block_reasons",
        "no_trade_intelligence",
        "explainability",
        "invalidation_level",
        "system_status",
        "trade_eligibility",
        "trade_plan",
        "trade_confidence",
    }
    assert final_decision["trade_decision"] == "Buy CE"
    assert final_decision["trade_eligibility"]["eligible"] is True
    assert final_decision["trade_plan"] is not None
    trade_confidence = final_decision["trade_confidence"]
    assert trade_confidence["score"] == final_decision["confluence_score"]
    assert "not probability of profit" in trade_confidence["meaning"]
    assert trade_confidence["factors"]
    assert all(
        set(factor) == {"name", "value", "direction", "weight", "contribution", "source", "timestamp", "available"}
        for factor in trade_confidence["factors"]
    )
    assert final_decision["selected_strategy"] != "none"
    assert final_decision["strategy_version"] != "0.0.0"
    assert final_decision["strategy"] != "none"
    assert final_decision["trade_quality"] in {"Excellent", "Good"}
    assert final_decision["confidence_label"] in {"High", "Medium", "Low", "Blocked"}
    assert result.factors["strategy_selection"]["selected_strategy"] == final_decision["strategy"]
    assert result.factors["strategy_selection"]["reason_selected"]
    assert isinstance(result.factors["strategy_selection"]["why_others_rejected"], list)
    assert 0 <= result.factors["probability_engine"]["probability_score"] <= 100
    assert result.factors["probability_engine"]["evidence"]
    assert result.decision_id

    record_recommendation_outcome(result.decision_id, outcome="WIN", pnl=500, actual_direction="BULLISH")
    metrics = recommendation_metrics()

    assert metrics["total_recommendations"] == 1
    assert metrics["buy_ce_count"] == 1
    assert metrics["no_trade_count"] == 0
    assert metrics["average_rr"] >= 1.5
    assert metrics["strategy_vs_outcome"]
    assert metrics["regime_vs_outcome"]
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
    no_trade = result.factors["final_decision"]["no_trade_intelligence"]
    assert result.factors["final_decision"]["trade_eligibility"]["eligible"] is False
    assert result.factors["final_decision"]["trade_plan"] is None
    assert no_trade["suggested_action"]
    assert no_trade["next_review_condition"]
    assert no_trade["reason_details"]
    assert all(
        set(detail) == {"code", "category", "severity", "message", "remediation"}
        for detail in no_trade["reason_details"]
    )
    assert all(detail["code"] == detail["code"].upper() for detail in no_trade["reason_details"])


def test_strategy_selection_uses_registry_metadata():
    engine = StrategyEngine(persist_governance=False)
    engine.configure_strategy("breakout", version="2.4.0")

    result = DecisionPipelineService(strategy_engine=engine).run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_bullish_candles(),
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
            candles_15m=_bullish_candles(),
            candles_1h=_bullish_candles(),
            oi_bias="BULLISH",
            pcr=1.1,
            put_oi=1200,
            call_oi=900,
            fii_cash=100,
            gift_nifty_bias="BULLISH",
        ),
        risk_blocked=False,
        persist=False,
    )

    selection = result.factors["strategy_selection"]
    assert selection["selected_strategy"] == "breakout"
    assert selection["strategy_version"] == "2.4.0"
    assert selection["scorecard"][0]["registry"]["supported_regimes"]


def test_strategy_selection_ignores_disabled_registry_strategy():
    engine = StrategyEngine(persist_governance=False)
    engine.configure_strategy("breakout", enabled=False, rollout_pct=0)

    result = DecisionPipelineService(strategy_engine=engine).run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_bullish_candles(),
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
            candles_15m=_bullish_candles(),
            candles_1h=_bullish_candles(),
            oi_bias="BULLISH",
            pcr=1.1,
            put_oi=1200,
            call_oi=900,
            fii_cash=100,
            gift_nifty_bias="BULLISH",
        ),
        risk_blocked=False,
        persist=False,
    )

    assert result.factors["strategy_selection"]["selected_strategy"] != "breakout"
    assert all(item["strategy"] != "breakout" for item in result.factors["strategy_selection"]["scorecard"])


def test_market_regime_returns_allowed_and_blocked_strategies():
    trend = analyze_trend(_bullish_candles())
    volume = analyze_volume(_bullish_candles())
    trending = analyze_market_regime(MarketDataInputs(candles=_bullish_candles()), volume, trend)
    volatile = analyze_market_regime(MarketDataInputs(candles=_bullish_candles(), india_vix=25), volume, trend)
    holiday = analyze_market_regime(MarketDataInputs(candles=_bullish_candles(), holiday_effect=True), volume, trend)

    assert trending["market_regime"] == "Trending"
    assert "breakout" in trending["allowed_strategies"]
    assert volatile["market_regime"] == "Volatile"
    assert "momentum" in volatile["blocked_strategies"]
    assert holiday["market_regime"] == "Holiday Effect"


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
    bullish_volume = analyze_volume(_bullish_candles())
    assert bullish_volume.supports_trade is True
    assert bullish_volume.volume_status == "BREAKOUT_CONFIRMED"
    assert bullish_volume.institutional_buying is True
    assert bullish_volume.details["volume_profile"]["poc"] is not None
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
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
            candles_15m=_bullish_candles(),
            candles_1h=_bullish_candles(),
            oi_bias="BULLISH",
            pcr=1.1,
            put_oi=1200,
            call_oi=900,
            fii_cash=100,
            gift_nifty_bias="BULLISH",
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
            candles_1m=_bearish_candles(),
            candles_5m=_bearish_candles(),
            candles_15m=_bearish_candles(),
            candles_1h=_bearish_candles(),
            oi_bias="BEARISH",
            pcr=0.8,
            put_oi=900,
            call_oi=1200,
            fii_cash=-100,
            gift_nifty_bias="BEARISH",
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
    assert bullish.factors["final_decision"]["trade_decision"] == "Buy CE"
    assert bearish.factors["final_decision"]["trade_decision"] == "Buy PE"
    assert blocked.factors["final_decision"]["trade_decision"] == "No Trade"
    assert blocked.factors["high_probability_trade_engine"]["paper_trade_gate"]["allowed"] is False
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
    assert result.factors["high_probability_trade_engine"]["paper_trade_gate"]["allowed"] is False
    assert "Data is stale." in result.factors["high_probability_trade_engine"]["paper_trade_gate"]["reasons"]


def test_paper_trade_gate_requires_risk_engine_pass():
    result = DecisionPipelineService().run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_bullish_candles(),
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
            candles_15m=_bullish_candles(),
            candles_1h=_bullish_candles(),
            oi_bias="BULLISH",
            pcr=1.1,
            put_oi=1200,
            call_oi=900,
            fii_cash=100,
            gift_nifty_bias="BULLISH",
        ),
        risk_blocked=True,
        persist=False,
    )

    gate = result.factors["high_probability_trade_engine"]["paper_trade_gate"]
    assert gate["allowed"] is False
    assert "Risk engine blocked the trade." in gate["reasons"]


def test_higher_timeframe_filter_blocks_conflict():
    result = analyze_higher_timeframe(
        MarketDataInputs(
            candles=_bullish_candles(),
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
            candles_15m=_bearish_candles(),
            candles_1h=_bullish_candles(),
        )
    )

    assert result["conflict"] is True
    assert result["passed"] is False


def test_higher_timeframe_filter_blocks_missing_required_series():
    result = analyze_higher_timeframe(
        MarketDataInputs(
            candles=_bullish_candles(),
            candles_1m=_bullish_candles(),
            candles_5m=_bullish_candles(),
        )
    )

    assert result["passed"] is False
    assert result["allowed_direction"] == "NONE"
    assert result["timeframes"]["15m"] == "UNAVAILABLE"
    assert result["timeframes"]["1h"] == "UNAVAILABLE"
    assert result["missing_required_timeframes"] == ["15m", "1h"]
    assert "unavailable" in result["reason"].lower()


def test_environment_market_context_does_not_silently_enter_decision_inputs(monkeypatch):
    monkeypatch.setenv("OI_BIAS", "BULLISH")
    monkeypatch.setenv("PCR", "1.25")
    validation = type("Validation", (), {"market_live": True, "valid_for_execution": True, "delay_seconds": 2, "warnings": []})()

    market = DecisionPipelineService().from_environment(validation=validation, candles=_bullish_candles())

    assert market.oi_bias is None
    assert market.pcr is None
    assert market.context_status["oi_bias"]["available"] is False
    assert any("Verified options context is unavailable" in warning for warning in market.warnings)


def test_verified_market_context_requires_source_timestamp_and_live_suitability():
    validation = type("Validation", (), {"market_live": True, "valid_for_execution": True, "delay_seconds": 2, "warnings": []})()
    timestamp = "2026-07-10T09:20:00+05:30"
    market = DecisionPipelineService().from_environment(
        validation=validation,
        candles=_bullish_candles(),
        market_context={
            "oi_bias": {"value": "BULLISH", "source": "dhan-option-chain", "timestamp": timestamp, "available": True, "live_suitable": True},
            "pcr": {"value": 1.25, "source": "dhan-option-chain", "timestamp": timestamp, "available": True, "live_suitable": True},
            "india_vix": {"value": 14.8, "source": "sample-fallback", "timestamp": timestamp, "available": True, "live_suitable": True},
        },
    )

    assert market.oi_bias == "BULLISH"
    assert market.pcr == 1.25
    assert market.india_vix is None
    assert market.context_status["oi_bias"]["available"] is True
    assert market.context_status["india_vix"]["available"] is False


def test_central_data_quality_gate_blocks_missing_options_and_required_timeframes():
    market = MarketDataInputs(
        candles=_bullish_candles(),
        candles_1m=_bullish_candles(),
        valid_for_execution=True,
        enforce_data_quality=True,
    )
    htf = analyze_higher_timeframe(market)

    quality = assess_trade_data_quality(market, htf)

    assert quality.usable_for_trade is False
    assert quality.status == "FAIL"
    assert any("verified options context unavailable" in reason for reason in quality.critical_errors)
    assert any("higher timeframes unavailable" in reason for reason in quality.critical_errors)


def test_central_data_quality_gate_blocks_duplicate_out_of_order_and_gapped_candles():
    def series(interval_minutes: int) -> list[dict]:
        base = datetime.fromisoformat("2026-07-10T09:15:00+05:30")
        rows = _bullish_candles()[:25]
        for index, row in enumerate(rows):
            row["timestamp"] = (base + timedelta(minutes=index * interval_minutes)).isoformat()
        return rows

    one_minute = series(1)
    one_minute[8]["timestamp"] = one_minute[7]["timestamp"]
    fifteen_minute = series(15)
    fifteen_minute[12]["timestamp"] = (datetime.fromisoformat(fifteen_minute[11]["timestamp"]) + timedelta(minutes=45)).isoformat()
    one_hour = series(60)
    market = MarketDataInputs(
        candles=one_minute,
        candles_1m=one_minute,
        candles_15m=fifteen_minute,
        candles_1h=one_hour,
        valid_for_execution=True,
        enforce_data_quality=True,
        context_status={"oi_bias": {"available": True}, "pcr": {"available": True}},
    )

    quality = assess_trade_data_quality(market, analyze_higher_timeframe(market))

    assert quality.usable_for_trade is False
    assert any("duplicate candle timestamps" in reason for reason in quality.critical_errors)
    assert any("out of order" in reason for reason in quality.critical_errors)
    assert any("unexpected interval gap" in reason for reason in quality.critical_errors)


def test_higher_timeframe_allows_ce_and_pe_direction():
    bullish = analyze_higher_timeframe(
        MarketDataInputs(candles_1m=_bullish_candles(), candles_5m=_bullish_candles(), candles_15m=_bullish_candles(), candles_1h=_bullish_candles())
    )
    bearish = analyze_higher_timeframe(
        MarketDataInputs(candles_1m=_bearish_candles(), candles_5m=_bearish_candles(), candles_15m=_bearish_candles(), candles_1h=_bearish_candles())
    )

    assert bullish["passed"] is True
    assert bullish["allowed_direction"] == "CE"
    assert bearish["passed"] is True
    assert bearish["allowed_direction"] == "PE"


def test_market_structure_detects_hh_hl_lh_ll_and_sideways():
    bullish = analyze_market_structure(_bullish_candles())
    bearish = analyze_market_structure(_bearish_candles())
    assert bullish["structure_bias"] == "Bullish"
    assert bullish["latest_event"] in {"HH_HL", "BOS"}
    assert bullish["swing_highs"]
    assert bullish["swing_lows"]
    assert bearish["structure_bias"] == "Bearish"
    assert bearish["latest_event"] in {"LH_LL", "BOS"}
    sideways = analyze_market_structure(_sideways_candles())
    assert sideways["latest_event"] == "Sideways"
    assert sideways["warning"]


def test_supply_demand_and_fvg_and_liquidity_detection():
    bullish = _bullish_candles()
    bearish = _bearish_candles()
    bullish_fvg = _bullish_candles()
    bullish_fvg[-3] = {"open": 108, "high": 110, "low": 106, "close": 109, "volume": 1200}
    bullish_fvg[-2] = {"open": 111, "high": 114, "low": 110, "close": 113, "volume": 1300}
    bullish_fvg[-1] = {"open": 121, "high": 128, "low": 120, "close": 126, "volume": 3000}
    bearish_fvg = _bearish_candles()
    bearish_fvg[-3] = {"open": 112, "high": 114, "low": 110, "close": 111, "volume": 1200}
    bearish_fvg[-2] = {"open": 108, "high": 109, "low": 104, "close": 105, "volume": 1300}
    bearish_fvg[-1] = {"open": 96, "high": 99, "low": 90, "close": 92, "volume": 3000}
    bullish_trend = analyze_trend(bullish)
    bearish_trend = analyze_trend(bearish)
    bullish_levels = analyze_support_resistance(bullish)
    liquidity_candles = _bullish_candles()
    liquidity_levels = analyze_support_resistance(liquidity_candles[:-1])
    liquidity_candles[-1] = {
        "open": float(liquidity_levels.support or 120) + 1,
        "high": float(liquidity_levels.support or 120) + 5,
        "low": float(liquidity_levels.support or 120) - 1,
        "close": float(liquidity_levels.support or 120) + 2,
        "volume": 3000,
    }

    assert analyze_supply_demand(bullish)["nearest_demand"] is not None
    assert analyze_supply_demand(bearish)["nearest_supply"] is not None
    assert analyze_fvg(bullish_fvg, bullish_trend, {"demand_zone": bullish_levels.support})["type"] == "BULLISH_FVG"
    assert analyze_fvg(bearish_fvg, bearish_trend, {"supply_zone": analyze_support_resistance(bearish).resistance})["type"] == "BEARISH_FVG"
    assert analyze_liquidity(liquidity_candles, liquidity_levels)["liquidity_event"] == "LIQUIDITY_SWEEP_BELOW_SUPPORT"


def test_price_action_requires_confirmation_for_trade():
    assert analyze_price_action(_bullish_candles())["confirmed"] is True
    assert analyze_price_action(_bullish_candles())["pattern"] == "BULLISH_ENGULFING"
    assert analyze_price_action(_bearish_candles())["pattern"] == "BEARISH_ENGULFING"
    result = DecisionPipelineService().run(
        MarketDataInputs(
            market_live=True,
            valid_for_execution=True,
            feed_delay_seconds=2,
            candles=_sideways_candles(),
            candles_1m=_sideways_candles(),
            candles_5m=_sideways_candles(),
            candles_15m=_sideways_candles(),
            candles_1h=_sideways_candles(),
            pcr=1.1,
            put_oi=1200,
            call_oi=900,
            fii_cash=100,
            gift_nifty_bias="BULLISH",
        ),
        risk_blocked=False,
        persist=False,
    )

    assert result.decision.trade_recommendation == "No Trade"
    assert "no price action confirmation" in result.factors["checklist_blockers"]


def test_discipline_blocks_fomo_chasing_and_average_quality_blocks_paper_trade():
    chasing = _bullish_candles()
    chasing[-1] = {"open": 120, "high": 160, "low": 119, "close": 159, "volume": 3000, "vwap": 125}
    result = DecisionPipelineService().run(
        MarketDataInputs(market_live=True, valid_for_execution=True, feed_delay_seconds=2, candles=chasing),
        risk_blocked=False,
        persist=False,
    )

    assert result.decision.trade_recommendation == "No Trade"
    assert any("chasing" in reason.lower() or "late entry" in reason.lower() for reason in result.factors["high_probability_trade_engine"]["paper_trade_gate"]["reasons"])
    assert result.factors["high_probability_trade_engine"]["paper_trade_gate"]["allowed"] is False
