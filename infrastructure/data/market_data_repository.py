from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd


class MarketDataRepository(Protocol):
    def load_ohlcv(self, symbol: str) -> pd.DataFrame:
        raise NotImplementedError


class CsvMarketDataRepository:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    def load_ohlcv(self, symbol: str) -> pd.DataFrame:
        path = self.data_dir / f"{symbol}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Market data file not found: {path}")
        return pd.read_csv(path)
