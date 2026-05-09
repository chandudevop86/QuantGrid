from abc import ABC, abstractmethod
from typing import List, Dict, Any


class MarketDataAdapter(ABC):

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        pass