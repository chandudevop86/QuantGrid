# Backend/Testing/test_trading_orchestrator.py

import sys
import os

sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../.."
        )
    )
)


from Backend.application.trading_orchestrator import TradingOrchestrator
from Backend.application.decision_pipeline import MarketDataInputs
from Backend.application.trade_repository import TradeRepository



def create_orchestrator():

    repository = TradeRepository()

    orchestrator = TradingOrchestrator(
        trade_repository=repository
    )

    return orchestrator



def test_execute_trade():

    print("\nTEST 1: Normal Trade\n")


    market = MarketDataInputs(

    symbol="NIFTY",

    market_live=True,

    valid_for_execution=True,

    trend="Strong Trend",

    momentum="Strong",

    price_action="Breakout",

    oi_bias="Bullish",

    pcr=1.0,

    vwap_relation="Above",

    india_vix=15,

    expiry_day=False,

    candles=[
        {
            "close":23800,
            "volume":100000
        }
    ]

)


    orchestrator = create_orchestrator()


    result = orchestrator.execute_cycle(
    market
)

    print(result)



def test_low_confidence():

    print("\nTEST 2: Low Confidence\n")


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


    orchestrator = create_orchestrator()


    result = orchestrator.execute_cycle(
    market
)

    print(result)



def test_expiry_day():

    print("\nTEST 3: Expiry Day\n")


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


    orchestrator = create_orchestrator()


    result = orchestrator.execute_cycle(
    market
)

    print(result)



if __name__ == "__main__":

    print("Running Trading Tests...\n")


    test_execute_trade()

    test_low_confidence()

    test_expiry_day()


    print("\nAll tests completed.")