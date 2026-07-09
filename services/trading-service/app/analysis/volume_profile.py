from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.application.volume_analysis import volume_profile as _volume_profile


def calculate_volume_profile(candles: list[dict[str, Any]], bins: int = 12) -> dict[str, Any]:
    frame = pd.DataFrame(candles)
    if frame.empty:
        return {"poc": None, "vah": None, "val": None, "hvn": [], "lvn": []}
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    return _volume_profile(frame, bins=bins)
