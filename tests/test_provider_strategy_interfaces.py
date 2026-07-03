from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.domain.engine.strategy_engine import StrategyEngine
from Backend.domain.shared import IMarketDataProvider, IStrategy
from Backend.infrastructure.market_data.yahoo_provider import YahooProvider


def test_yahoo_provider_implements_market_data_provider_contract():
    provider = YahooProvider()

    assert isinstance(provider, IMarketDataProvider)
    assert callable(provider.candles)
    assert callable(provider.status)


def test_registered_strategies_implement_strategy_contract():
    engine = StrategyEngine()

    assert engine.available()
    for strategy in engine._strategies.values():
        assert isinstance(strategy, IStrategy)
        assert callable(strategy.generate_signal)
        assert callable(strategy.validate_inputs)
        assert callable(strategy.explain_signal)
