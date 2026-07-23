# test_trading_orchestrator.py

from Backend.application.trading_orchestrator import TradingOrchestrator
from Backend.application.models.market import MarketDataInputs


def test_execute_trade():

    market = MarketDataInputs(
        trend="Strong Trend",
        market_regime="Trending",
        volume="High",
        volatility="High",
        oi_bias="Bullish",
        pcr=1.0,
        vwap_relation="Above",
        atr=120,
        spread=0.4,
        news=False,
        institutional=True,
        expiry_day=False,
    )

    orchestrator = TradingOrchestrator()

    orchestrator.execute(
        market=market,
        strategy="breakout",
    )


def test_low_confidence():

    market = MarketDataInputs(
        trend="Weak",
        market_regime="Range",
        volume="Low",
        volatility="Low",
        oi_bias="Bearish",
        pcr=0.4,
        vwap_relation="Below",
        atr=10,
        spread=3.5,
        news=True,
        institutional=False,
        expiry_day=False,
    )

    orchestrator = TradingOrchestrator()

    orchestrator.execute(
        market=market,
        strategy="mean_reversion",
    )


def test_expiry_day():

    market = MarketDataInputs(
        trend="Strong Trend",
        market_regime="Trending",
        volume="High",
        volatility="High",
        oi_bias="Bullish",
        pcr=0.95,
        vwap_relation="Above",
        atr=140,
        spread=0.2,
        news=False,
        institutional=True,
        expiry_day=True,
    )

    orchestrator = TradingOrchestrator()

    orchestrator.execute(
        market=market,
        strategy="btst",
    )


if __name__ == "__main__":
    print("Running Trading Tests...\n")

    test_execute_trade()
    test_low_confidence()
    test_expiry_day()

    print("\nAll tests completed.")