from __future__ import annotations

import pandas as pd

from Backend.domain.market_data.validator import MarketDataValidator


def _candles():
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-10-20", periods=30, freq="min", tz="UTC"),
            "open": [100.0] * 30,
            "high": [102.0] * 30,
            "low": [99.0] * 30,
            "close": [101.0] * 30,
            "volume": [100] * 30,
        }
    )


def test_valid_data_is_quiet_by_default(monkeypatch, capsys):
    monkeypatch.delenv("QUANTGRID_MARKET_DATA_VALIDATOR_VERBOSE", raising=False)
    result = MarketDataValidator.validate(_candles())
    assert result.valid
    assert result.errors == []
    assert capsys.readouterr().out == ""


def test_invalid_data_still_rejected_when_quiet(monkeypatch, capsys):
    monkeypatch.delenv("QUANTGRID_MARKET_DATA_VALIDATOR_VERBOSE", raising=False)
    candles = _candles()
    candles.loc[5, "high"] = 98.0
    result = MarketDataValidator.validate(candles)
    assert not result.valid
    assert "High < Low" in result.errors
    assert "High < Open" in result.errors
    assert "High < Close" in result.errors
    assert capsys.readouterr().out == ""


def test_verbose_mode_keeps_diagnostics(monkeypatch, capsys):
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_VALIDATOR_VERBOSE", "1")
    result = MarketDataValidator.validate(_candles())
    assert result.valid
    output = capsys.readouterr().out
    assert "MARKET DATA VALIDATOR" in output
    assert "Market data validation PASSED" in output
