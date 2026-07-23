from .env import BROKER

class Settings:

    DEFAULT_CAPITAL = 100000

    MAX_OPEN_TRADES = 5

    RISK_PERCENT = 2

    DEFAULT_BROKER = BROKER

settings = Settings()