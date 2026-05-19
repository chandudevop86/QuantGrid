from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from Backend.domain.models.signal import StrategySignal


@dataclass(slots=True)
class GlobalRiskConfig:
    starting_equity: float = 100_000.0
    max_daily_loss_pct: float = 3.0
    max_trades_per_day: int = 3
    max_drawdown_pct: float = 10.0
    min_signal_score: float = 10.0
    max_stale_seconds: int = 60


@dataclass(slots=True)
class RiskSnapshot:
    equity: float
    peak_equity: float
    daily_pnl: float
    trades_today: int
    kill_switch_active: bool
    reason: str | None = None


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
        now = now or datetime.utcnow()
        if self.kill_switch_active:
            return False, "kill_switch_active"
        if self._score(signal) < float(self.config.min_signal_score):
            return False, "signal_score_below_threshold"
        age = (now.replace(tzinfo=None) - signal.signal_time.replace(tzinfo=None)).total_seconds()
        if age > int(self.config.max_stale_seconds):
            return False, "stale_signal"
        if self.trades_for(now.date()) >= int(self.config.max_trades_per_day):
            return False, "max_trades_per_day_exceeded"
        if self.daily_loss_pct(now.date()) >= float(self.config.max_daily_loss_pct):
            return False, "max_daily_loss_exceeded"
        if self.drawdown_pct() >= float(self.config.max_drawdown_pct):
            self.kill_switch_active = True
            return False, "max_drawdown_exceeded"
        return True, "accepted"

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
