from __future__ import annotations

from math import floor

from app.domain.models.signal import StrategySignal


class RiskManager:
    def risk_fraction(self, risk_pct: float) -> float:
        value = float(risk_pct or 0.0)
        return value / 100.0 if value > 1 else value

    def position_size(self, capital: float, risk_pct: float, entry: float, stop_loss: float) -> int:
        risk_per_unit = abs(float(entry) - float(stop_loss))
        if risk_per_unit <= 0:
            return 0
        risk_amount = max(0.0, float(capital)) * self.risk_fraction(risk_pct)
        if risk_amount <= 0:
            return 1
        return max(1, floor(risk_amount / risk_per_unit))

    def validate_signal(self, signal: StrategySignal) -> bool:
        if signal.entry_price <= 0 or signal.stop_loss <= 0 or signal.target_price <= 0:
            return False
        if signal.side == "BUY":
            return signal.stop_loss < signal.entry_price < signal.target_price
        if signal.side == "SELL":
            return signal.target_price < signal.entry_price < signal.stop_loss
        return False
