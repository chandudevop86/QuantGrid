from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    strategy: str
    symbol: str
    side: str
    entry: float
    stop_loss: float
    target: float
    quantity: int
    entry_time: str
    exit_time: str
    exit_price: float
    pnl: float
    rr: float
    outcome: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    strategy: str
    symbol: str
    metrics: dict[str, float | int]
    trades: list[BacktestTrade] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "metrics": self.metrics,
            "trades": [trade.to_dict() for trade in self.trades],
        }
