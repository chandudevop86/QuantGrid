from __future__ import annotations

import sys
from pathlib import Path

TRADING_SERVICE = Path(__file__).resolve().parents[5] / "services" / "trading-service"

if str(TRADING_SERVICE) not in sys.path:
    sys.path.insert(0, str(TRADING_SERVICE))

from Backend.presentation.api.main import app  # noqa: E402

__all__ = ["app"]
