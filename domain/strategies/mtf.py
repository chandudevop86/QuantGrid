from __future__ import annotations

from domain.strategies.mean_reversion import MeanReversionStrategy


class MTFStrategy(MeanReversionStrategy):
    name = "MTF"
