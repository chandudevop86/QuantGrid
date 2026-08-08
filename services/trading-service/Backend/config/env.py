from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)

BROKER = os.getenv("QUANTGRID_BROKER_PROVIDER")
DATABASE_URL = os.getenv("DATABASE_URL")
MARKET_PROVIDER = os.getenv("QUANTGRID_MARKET_DATA_PROVIDER")
CAPITAL = int(os.getenv("QUANTGRID_CAPITAL", "100000"))
RISK_PER_TRADE = float(os.getenv("QUANTGRID_RISK_PER_TRADE_PCT", "1"))