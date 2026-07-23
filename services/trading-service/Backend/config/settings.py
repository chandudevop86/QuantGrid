"""
Backend/config/settings.py

Centralized application settings.
"""

from .env import (
    BROKER,
    MARKET_PROVIDER,
    CAPITAL,
    RISK_PER_TRADE,
    DATABASE_URL,
)

class Settings:
    # Broker
    DEFAULT_BROKER = BROKER

    # Market
    MARKET_PROVIDER = MARKET_PROVIDER
    DEFAULT_INTERVAL = "5m"
    DEFAULT_EXCHANGE = "NSE"
    ALLOW_YAHOO = True

    # Trading
    DEFAULT_CAPITAL = CAPITAL
    RISK_PERCENT = RISK_PER_TRADE
    MAX_OPEN_TRADES = 5

    # Broker credentials
    CLIENT_ID = ""
    ACCESS_TOKEN = ""

    # Features
    LIVE_TRADING = False
    ENABLE_AI = True
    ENABLE_PAPER_TRADING = True

    # Database
    DATABASE_URL = DATABASE_URL

settings = Settings()