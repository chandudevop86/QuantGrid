from __future__ import annotations

from app.narratives.fo_narrative_loop import MarketRegime, NarrativeInput, OptionBias, generate_narrative_signal


def _chain(
    *,
    call_change: float = 100,
    put_change: float = 100,
    call_oi_100: float = 1000,
    call_oi_110: float = 4000,
    put_oi_100: float = 4000,
    put_oi_110: float = 1000,
):
    return [
        {
            "strike": 100,
            "ce": {"oi": call_oi_100, "oi_change": call_change, "volume": 2000},
            "pe": {"oi": put_oi_100, "oi_change": put_change, "volume": 2200},
        },
        {
            "strike": 110,
            "ce": {"oi": call_oi_110, "oi_change": call_change, "volume": 2300},
            "pe": {"oi": put_oi_110, "oi_change": put_change, "volume": 1900},
        },
    ]


def _input(**overrides) -> NarrativeInput:
    data = {
        "symbol": "NIFTY",
        "spot_price": 105,
        "futures_price": 105.2,
        "previous_spot": 104.8,
        "option_chain": _chain(),
        "pcr": 1.05,
        "india_vix": 13.5,
        "india_vix_change_pct": 0.5,
        "fii_cash": 500,
        "dii_cash": 100,
        "fii_index_futures": 250,
        "gift_nifty_change_pct": 0.2,
        "global_market_cues": 0.3,
        "max_pain": 105,
        "days_to_expiry": 3,
    }
    data.update(overrides)
    return NarrativeInput(**data)


def test_bullish_breakout_generates_buy_ce():
    signal = generate_narrative_signal(
        _input(
            spot_price=112,
            futures_price=112.3,
            previous_spot=109,
            option_chain=_chain(call_change=-200, put_change=900),
            pcr=1.1,
            max_pain=110,
        )
    )

    assert signal.signal == OptionBias.BUY_CE
    assert signal.market_regime == MarketRegime.BULLISH
    assert "Resistance breakout" in signal.detected_patterns
    assert "why" in signal.explanation.lower()
    assert signal.key_levels["invalidation"] == 110


def test_bearish_breakdown_generates_buy_pe():
    signal = generate_narrative_signal(
        _input(
            spot_price=98,
            futures_price=97.7,
            previous_spot=101,
            option_chain=_chain(call_change=900, put_change=100),
            pcr=0.9,
            fii_cash=-600,
            fii_index_futures=-400,
            gift_nifty_change_pct=-0.4,
            global_market_cues=-0.3,
            max_pain=100,
        )
    )

    assert signal.signal == OptionBias.BUY_PE
    assert signal.market_regime == MarketRegime.BEARISH
    assert "Support breakdown" in signal.detected_patterns
    assert signal.key_levels["invalidation"] == 100


def test_sideways_range_returns_no_trade():
    signal = generate_narrative_signal(_input(spot_price=105, option_chain=_chain()))

    assert signal.signal == OptionBias.NO_TRADE
    assert signal.market_regime == MarketRegime.SIDEWAYS
    assert "inside" in signal.reason.lower()


def test_expiry_trap_avoids_far_otm_options():
    signal = generate_narrative_signal(
        _input(
            spot_price=105.1,
            is_expiry_day=True,
            days_to_expiry=0,
            pcr=1.45,
            max_pain=105,
            option_chain=_chain(call_change=700, put_change=800),
        )
    )

    assert signal.signal == OptionBias.NO_TRADE
    assert signal.market_regime == MarketRegime.EXPIRY_TRAP
    assert "avoid far OTM".lower() in signal.expiry_warning.lower()
    assert "premium crush" in signal.expiry_warning.lower()


def test_high_vix_false_breakout_reduces_confidence_and_no_trade():
    signal = generate_narrative_signal(
        _input(
            spot_price=112,
            futures_price=112.1,
            previous_spot=109,
            option_chain=_chain(call_change=800, put_change=-200),
            pcr=1.55,
            india_vix=21,
            india_vix_change_pct=8,
            max_pain=110,
        )
    )

    assert signal.signal == OptionBias.NO_TRADE
    assert signal.market_regime == MarketRegime.VOLATILE
    assert "Fake breakout" in signal.detected_patterns
    assert signal.confidence < 60


def test_trading_narrative_endpoint_returns_json(app_client, monkeypatch):
    from Backend.presentation.api import trading_api
    from conftest import admin_headers

    expected = generate_narrative_signal(_input())
    monkeypatch.setattr(trading_api, "run_fno_narrative", lambda symbol: expected)

    response = app_client.get("/trading/narrative/fno?symbol=NIFTY", headers=admin_headers(app_client))

    assert response.status_code == 200
    assert response.json()["signal"] == "NO_TRADE"
    assert response.json()["explanation"]
