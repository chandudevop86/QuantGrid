from .env import BROKER

class Settings:

    DEFAULT_CAPITAL = 100000

    MAX_OPEN_TRADES = 5

    RISK_PERCENT = 2

    DEFAULT_BROKER = BROKER

settings = Settings()
from .env import (
    BROKER,
    MARKET_PROVIDER,
    CAPITAL,
    RISK_PER_TRADE,
)

class Settings:
    DEFAULT_BROKER = BROKER
    MARKET_PROVIDER = MARKET_PROVIDER
    DEFAULT_CAPITAL = CAPITAL
    RISK_PERCENT = RISK_PER_TRADE

settings = Settings()