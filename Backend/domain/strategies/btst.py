from __future__ import annotations

from Backend.domain.strategies.mean_reversion import MeanReversionStrategy


class BTSTStrategy(MeanReversionStrategy):
    name = "BTST"
