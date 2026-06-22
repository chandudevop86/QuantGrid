from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import floor
from typing import Any

from Backend.domain.models.signal import StrategySignal


@dataclass(slots=True)
class GlobalRiskConfig:
    starting_equity: float = 100_000.0
    max_daily_loss_pct: float = 3.0
    max_trades_per_day: int = 3
    max_drawdown_pct: float = 10.0
    min_signal_score: float = 10.0
    max_stale_seconds: int = 60
    max_risk_per_trade_pct: float = 2.0


@dataclass(slots=True)
class RiskSnapshot:
    equity: float
    peak_equity: float
    daily_pnl: float
    trades_today: int
    kill_switch_active: bool
    reason: str | None = None


@dataclass(slots=True)
class RiskDecision:
    accepted: bool
    reason: str
    quantity: int = 0
    risk_amount: float = 0.0
    risk_per_unit: float = 0.0
    risk_pct: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.accepted

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "allowed": self.accepted,
            "reason": self.reason,
            "quantity": self.quantity,
            "risk_amount": self.risk_amount,
            "risk_per_unit": self.risk_per_unit,
            "risk_pct": self.risk_pct,
            "metadata": self.metadata,
        }


class GlobalRiskManager:
    def __init__(self, config: GlobalRiskConfig | None = None) -> None:
        self.config = config or GlobalRiskConfig()
        self.equity = float(self.config.starting_equity)
        self.peak_equity = float(self.config.starting_equity)
        self.daily_pnl: dict[date, float] = {}
        self.daily_trades: dict[date, int] = {}
        self.kill_switch_active = False
        self.rejections: list[str] = []

    def validate_signal(self, signal: StrategySignal, *, now: datetime | None = None) -> tuple[bool, str]:
        decision = self.validate_order(signal, now=now)
        return decision.accepted, decision.reason

    def validate_order(
        self,
        signal: StrategySignal,
        *,
        now: datetime | None = None,
        capital: float | None = None,
    ) -> RiskDecision:
        now = now or datetime.utcnow()
        if self.kill_switch_active:
            return self._reject("kill_switch_active")
        levels_valid, levels_reason = self._valid_levels(signal)
        if not levels_valid:
            return self._reject(levels_reason)
        if self._score(signal) < float(self.config.min_signal_score):
            return self._reject("signal_score_below_threshold")
        requested_risk_pct = self._risk_pct(signal)
        risk_pct = requested_risk_pct if requested_risk_pct is not None else min(1.0, float(self.config.max_risk_per_trade_pct))
        if risk_pct > float(self.config.max_risk_per_trade_pct):
            return self._reject("max_risk_per_trade_exceeded", risk_pct=risk_pct)
        age = (now.replace(tzinfo=None) - signal.signal_time.replace(tzinfo=None)).total_seconds()
        if age > int(self.config.max_stale_seconds):
            return self._reject("stale_signal", risk_pct=risk_pct)
        if self.trades_for(now.date()) >= int(self.config.max_trades_per_day):
            return self._reject("max_trades_per_day_exceeded", risk_pct=risk_pct)
        if self.daily_loss_pct(now.date()) >= float(self.config.max_daily_loss_pct):
            return self._reject("max_daily_loss_exceeded", risk_pct=risk_pct)
        if self.drawdown_pct() >= float(self.config.max_drawdown_pct):
            self.kill_switch_active = True
            return self._reject("max_drawdown_exceeded", risk_pct=risk_pct)
        metadata = signal.metadata or {}
        quantity_cap = metadata.get("max_quantity", metadata.get("quantity"))
        quantity, risk_amount, risk_per_unit = self.position_size(
            capital=self.equity if capital is None else capital,
            risk_pct=risk_pct,
            entry=signal.entry_price,
            stop_loss=signal.stop_loss,
            lot_size=int(metadata.get("lot_size", 1) or 1),
            max_quantity=quantity_cap,
        )
        if quantity <= 0:
            return self._reject("position_size_zero", risk_pct=risk_pct, risk_per_unit=risk_per_unit, risk_amount=risk_amount)
        return RiskDecision(
            accepted=True,
            reason="accepted",
            quantity=quantity,
            risk_amount=risk_amount,
            risk_per_unit=risk_per_unit,
            risk_pct=risk_pct,
            metadata={"score": self._score(signal), "age_seconds": age},
        )

    def position_size(
        self,
        *,
        capital: float,
        risk_pct: float,
        entry: float,
        stop_loss: float | None,
        lot_size: int = 1,
        max_quantity: Any | None = None,
    ) -> tuple[int, float, float]:
        if stop_loss is None:
            return 0, 0.0, 0.0
        risk_per_unit = abs(float(entry) - float(stop_loss))
        if risk_per_unit <= 0:
            return 0, 0.0, risk_per_unit
        risk_amount = max(0.0, float(capital)) * self._risk_fraction(risk_pct)
        if risk_amount <= 0:
            return 0, risk_amount, risk_per_unit
        raw_quantity = floor(risk_amount / risk_per_unit)
        lot = max(1, int(lot_size or 1))
        quantity = max(0, (raw_quantity // lot) * lot)
        if quantity == 0 and raw_quantity > 0:
            quantity = lot if risk_per_unit * lot <= risk_amount else 0
        if max_quantity is not None:
            quantity = min(quantity, int(max_quantity))
        return int(quantity), float(risk_amount), float(risk_per_unit)

    def record_trade_opened(self, when: datetime | None = None) -> None:
        trade_date = (when or datetime.utcnow()).date()
        self.daily_trades[trade_date] = self.daily_trades.get(trade_date, 0) + 1

    def record_realized_pnl(self, pnl: float, when: datetime | None = None) -> RiskSnapshot:
        trade_date = (when or datetime.utcnow()).date()
        self.equity += float(pnl)
        self.peak_equity = max(self.peak_equity, self.equity)
        self.daily_pnl[trade_date] = self.daily_pnl.get(trade_date, 0.0) + float(pnl)
        if self.daily_loss_pct(trade_date) >= float(self.config.max_daily_loss_pct):
            self.kill_switch_active = True
        if self.drawdown_pct() >= float(self.config.max_drawdown_pct):
            self.kill_switch_active = True
        return self.snapshot(trade_date)

    def snapshot(self, trade_date: date | None = None) -> RiskSnapshot:
        trade_date = trade_date or datetime.utcnow().date()
        return RiskSnapshot(
            equity=self.equity,
            peak_equity=self.peak_equity,
            daily_pnl=self.daily_pnl.get(trade_date, 0.0),
            trades_today=self.daily_trades.get(trade_date, 0),
            kill_switch_active=self.kill_switch_active,
        )

    def trades_for(self, trade_date: date) -> int:
        return self.daily_trades.get(trade_date, 0)

    def daily_loss_pct(self, trade_date: date) -> float:
        loss = min(0.0, self.daily_pnl.get(trade_date, 0.0))
        return abs(loss) / max(float(self.config.starting_equity), 1.0) * 100.0

    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)

    @staticmethod
    def _score(signal: StrategySignal) -> float:
        for key in ("total_score", "score"):
            if key in signal.metadata:
                return float(signal.metadata[key])
        return 0.0

    @staticmethod
    def _valid_levels(signal: StrategySignal) -> tuple[bool, str]:
        if signal.stop_loss is None:
            return False, "missing_stop_loss"
        if signal.target_price is None:
            return False, "missing_target"
        entry = float(signal.entry_price)
        stop = float(signal.stop_loss)
        target = float(signal.target_price)
        if entry <= 0 or stop <= 0 or target <= 0:
            return False, "invalid_signal_levels"
        if signal.side.upper() == "BUY":
            return (True, "accepted") if stop < entry < target else (False, "invalid_buy_levels")
        if signal.side.upper() == "SELL":
            return (True, "accepted") if target < entry < stop else (False, "invalid_sell_levels")
        return False, "invalid_signal_side"

    @staticmethod
    def _risk_pct(signal: StrategySignal) -> float | None:
        metadata = signal.metadata or {}
        for key in ("risk_pct", "risk_per_trade_pct"):
            if key in metadata:
                return float(metadata[key])
        return None

    @staticmethod
    def _risk_fraction(risk_pct: float) -> float:
        value = float(risk_pct or 0.0)
        return value / 100.0 if value >= 1 else value

    @staticmethod
    def _reject(reason: str, **metadata: Any) -> RiskDecision:
        return RiskDecision(False, reason, metadata={key: value for key, value in metadata.items() if value is not None})
