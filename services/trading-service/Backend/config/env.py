from dotenv import load_dotenv
import os

load_dotenv()

BROKER = os.getenv("QUANTGRID_BROKER_PROVIDER")

DATABASE_URL = os.getenv("DATABASE_URL")

MARKET_PROVIDER = os.getenv("QUANTGRID_MARKET_DATA_PROVIDER")

CAPITAL = int(os.getenv("QUANTGRID_CAPITAL", "100000"))

RISK_PER_TRADE = float(os.getenv("QUANTGRID_RISK_PER_TRADE_PCT", "1"))