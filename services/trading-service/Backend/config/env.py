from pathlib import Path
import os

from dotenv import load_dotenv


# ==================================================
# Environment Configuration
# ==================================================

# Project root:
# services/trading-service/
BASE_DIR = Path(__file__).resolve().parents[2]

ENV_FILE = BASE_DIR / ".env"


# Load environment variables
load_dotenv(
    dotenv_path=ENV_FILE,
    override=False,
)


# ==================================================
# Broker Configuration
# ==================================================

BROKER = os.getenv(
    "QUANTGRID_BROKER_PROVIDER",
    "dhan",
)


# ==================================================
# Market Data Configuration
# ==================================================

MARKET_PROVIDER = os.getenv(
    "QUANTGRID_MARKET_DATA_PROVIDER",
    "dhan",
)


# ==================================================
# Database Configuration
# ==================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
)


if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. "
        "Please configure it in .env"
    )


# ==================================================
# Trading Capital & Risk Management
# ==================================================

CAPITAL = int(
    os.getenv(
        "QUANTGRID_CAPITAL",
        "100000",
    )
)


RISK_PER_TRADE = float(
    os.getenv(
        "QUANTGRID_RISK_PER_TRADE_PCT",
        "1",
    )
)


# ==================================================
# Application Settings
# ==================================================

ENVIRONMENT = os.getenv(
    "QUANTGRID_ENV",
    "development",
)


DEBUG = os.getenv(
    "QUANTGRID_DEBUG",
    "false",
).lower() == "true"


LOG_LEVEL = os.getenv(
    "QUANTGRID_LOG_LEVEL",
    "INFO",
)


# ==================================================
# Provider Validation
# ==================================================

SUPPORTED_BROKERS = [
    "dhan",
    "paper",
]


SUPPORTED_MARKET_PROVIDERS = [
    "dhan",
    "yahoo",
]


if BROKER not in SUPPORTED_BROKERS:
    raise RuntimeError(
        f"Unsupported broker provider: {BROKER}. "
        f"Allowed: {SUPPORTED_BROKERS}"
    )


if MARKET_PROVIDER not in SUPPORTED_MARKET_PROVIDERS:
    raise RuntimeError(
        f"Unsupported market provider: {MARKET_PROVIDER}. "
        f"Allowed: {SUPPORTED_MARKET_PROVIDERS}"
    )


# ==================================================
# Debug Output Helper
# ==================================================

def get_config():

    return {
        "environment": ENVIRONMENT,
        "broker": BROKER,
        "market_provider": MARKET_PROVIDER,
        "capital": CAPITAL,
        "risk_per_trade": RISK_PER_TRADE,
        "database": "configured" if DATABASE_URL else "missing",
    }