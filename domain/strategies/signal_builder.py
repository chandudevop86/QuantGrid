from __future__ import annotations

from typing import Any

import pandas as pd

from app.domain.models.signal import StrategySignal
from app.domain.risk.risk_manager import RiskManager


class SignalBuilder:
    def __init__(self, risk_manager: RiskManager | None = None) -> None:
        self.risk_manager = risk_manager or RiskManager()

    def build(self, row: pd.Series, *, strategy_name: str, symbol: str, side: str, capital: float, risk_pct: float, stop_loss: float, target_price: float, score: float, metadata: dict[str, Any] | None = None) -> StrategySignal | None:
        entry = float(row["close"])
        quantity = self.risk_manager.position_size(capital, risk_pct, entry, stop_loss)
        if quantity <= 0:
            return None
        signal_metadata = {"quantity": int(quantity), "total_score": round(float(score), 2), "score": round(float(score), 2)}
        signal_metadata.update(self._indicator_metadata(row))
        signal_metadata.update(metadata or {})
        return StrategySignal(
            strategy_name=strategy_name,
            symbol=symbol,
            side=side.upper(),
            entry_price=round(entry, 4),
            stop_loss=round(float(stop_loss), 4),
            target_price=round(float(target_price), 4),
            signal_time=pd.Timestamp(row["timestamp"]).to_pydatetime(),
            metadata=signal_metadata,
        )

    def _indicator_metadata(self, row: pd.Series) -> dict[str, float]:
        keys = ["ema_9", "ema_21", "ema_50", "ema_200", "rsi", "macd", "macd_signal", "macd_hist", "vwap"]
        output: dict[str, float] = {}
        for key in keys:
            if key in row:
                output[key] = round(float(row[key]), 4)
        if "rsi" in output:
            output["rsi"] = round(output["rsi"], 2)
        return output
