from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

import numpy as np
import pandas as pd

from Backend.application.trading_service import TradingService
from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.risk import GlobalRiskManager
from Backend.trading_system.slippage import SlippageModel


@dataclass
class Trade:
    id: str
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    raw