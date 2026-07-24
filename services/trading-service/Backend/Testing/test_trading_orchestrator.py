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
        "timestamp": "2026-07-24T09:15:00",
        "open": 23750,
        "high": 23850,
        "low": 23720,
        "close": 23800,
        "volume": 100000
    },
    {
        "timestamp": "2026-07-24T09:20:00",
        "open": 23800,
        "high": 23880,
        "low": 23790,
        "close": 23850,
        "volume": 120000
    },
    {
        "timestamp": "2026-07-24T09:25:00",
        "open": 23850,
        "high": 23900,
        "low": 23830,
        "close": 23870,
        "volume": 110000
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

    symbol="NIFTY",

    market_live=True,

    valid_for_execution=True,

    trend="Weak",

    momentum="Weak",

    price_action="Range",

    oi_bias="Bearish",

    pcr=0.4,

    vwap_relation="Below",

    liquidity="Low",

    expiry_day=False,

    capital=100000,

    risk_per_trade=1500,

    candles=[
        {
            "timestamp": "2026-07-24T09:15:00",
            "open": 23800,
            "high": 23820,
            "low": 23780,
            "close": 23790,
            "volume": 50000
        },
        {
            "timestamp": "2026-07-24T09:20:00",
            "open": 23790,
            "high": 23800,
            "low": 23750,
            "close": 23760,
            "volume": 45000
        }
    ]
)


    orchestrator = create_orchestrator()


    result = orchestrator.execute_cycle(
    market
)

    print(result)



def test_expiry_day():

    print("\nTEST 3: Expiry Day\n")


    market = MarketDataInputs(

    symbol="NIFTY",

    market_live=True,

    valid_for_execution=True,

    trend="Strong Trend",

    momentum="Strong",

    price_action="Breakout",

    oi_bias="Bullish",

    pcr=0.95,

    vwap_relation="Above",

    liquidity="High",

    expiry_day=True,

    capital=100000,

    risk_per_trade=1500,

    candles=[
        {
            "timestamp": "2026-07-24T09:15:00",
            "open": 23800,
            "high": 23900,
            "low": 23790,
            "close": 23880,
            "volume": 150000
        },
        {
            "timestamp": "2026-07-24T09:20:00",
            "open": 23880,
            "high": 23950,
            "low": 23870,
            "close": 23920,
            "volume": 180000
        },
        {
            "timestamp": "2026-07-24T09:25:00",
            "open": 23920,
            "high": 23980,
            "low": 23910,
            "close": 23960,
            "volume": 200000
        }
    ]
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