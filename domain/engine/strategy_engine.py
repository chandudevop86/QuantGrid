from __future__ import annotations

from typing import Any

from app.domain.models.context import StrategyContext
from app.domain.models.signal import StrategySignal
from app.domain.strategies.amd import AMDStrategy
from app.domain.strategies.base import BaseStrategy
from app.domain.strategies.breakout import BreakoutStrategy
from app.domain.strategies.btst import BTSTStrategy
from app.domain.strategies.mean_reversion import MeanReversionStrategy
from app.domain.strategies.mtf import MTFStrategy
from app.domain.strategies.supply_demand import SupplyDemandStrategy


class StrategyEngine:
    def __init__(self, strategies: dict[str, BaseStrategy] | None = None) -> None:
        self._strategies: dict[str, BaseStrategy] = strategies or {}
        if not strategies:
            self.register("amd", AMDStrategy())
            self.register("breakout", BreakoutStrategy())
            self.register("mean_reversion", MeanReversionStrategy())
            self.register("supply_demand", SupplyDemandStrategy())
            self.register("mtf", MTFStrategy())
            self.register("btst", BTSTStrategy())

    def register(self, name: str, strategy: BaseStrategy) -> None:
        self._strategies[self._normalize(name)] = strategy

    def available(self) -> list[str]:
        return sorted(self._strategies)

    def run(self, strategy_name: str, data: Any, context: StrategyContext) -> list[StrategySignal]:
        strategy = self._strategies.get(self._normalize(strategy_name))
        if strategy is None:
            raise ValueError(f"Unknown strategy '{strategy_name}'. Available: {', '.join(self.available())}")
        return strategy.run(data, context)

    def run_many(self, strategy_names: list[str], data: Any, context: StrategyContext) -> dict[str, list[StrategySignal]]:
        return {name: self.run(name, data, context) for name in strategy_names}

    def _normalize(self, name: str) -> str:
        return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
