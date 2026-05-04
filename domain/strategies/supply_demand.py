from __future__ import annotations

from domain.strategies.mean_reversion import MeanReversionStrategy


class SupplyDemandStrategy(MeanReversionStrategy):
    name = "Supply Demand"
