from __future__ import annotations

from app.domain.strategies.mean_reversion import MeanReversionStrategy


class MTFStrategy(MeanReversionStrategy):
    name = "MTF"
