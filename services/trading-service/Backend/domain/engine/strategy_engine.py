from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.shared import IStrategy
from Backend.domain.strategies.amd import AMDStrategy
from Backend.domain.strategies.breakout import BreakoutStrategy
from Backend.domain.strategies.btst import BTSTStrategy
from Backend.domain.strategies.crt_tbs import CRTTBSStrategy
from Backend.domain.strategies.mean_reversion import MeanReversionStrategy
from Backend.domain.strategies.mtf import MTFStrategy
from Backend.domain.strategies.mtfa import MTFAStrategy
from Backend.domain.strategies.supply_demand import SupplyDemandStrategy


@dataclass(slots=True)
class StrategyGovernance:
    name: str
    version: str = "1.0.0"
    enabled: bool = True
    rollout_pct: int = 100
    supported_regimes: list[str] = field(default_factory=lambda: ["Any"])
    owner: str = "quantgrid"
    notes: str = "Default MVP strategy."
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyEngine:
    def __init__(self, strategies: dict[str, IStrategy] | None = None) -> None:
        self._strategies: dict[str, IStrategy] = strategies or {}
        self._governance: dict[str, StrategyGovernance] = {}
        self._audit_trail: list[dict[str, Any]] = []
        if strategies:
            for name in self._strategies:
                normalized = self._normalize(name)
                self._governance[normalized] = StrategyGovernance(name=normalized)
        else:
            self.register("amd", AMDStrategy())
            self.register("breakout", BreakoutStrategy())
            self.register("mean_reversion", MeanReversionStrategy())
            self.register("supply_demand", SupplyDemandStrategy())
            self.register("mtf", MTFStrategy())
            self.register("mtfa", MTFAStrategy())
            self.register("btst", BTSTStrategy())
            self.register("cbt", CRTTBSStrategy())
            self.register("crt_tbs", CRTTBSStrategy())

    def register(
        self,
        name: str,
        strategy: IStrategy,
        *,
        version: str = "1.0.0",
        enabled: bool = True,
        rollout_pct: int = 100,
        supported_regimes: list[str] | None = None,
    ) -> None:
        normalized = self._normalize(name)
        self._strategies[normalized] = strategy
        self._governance[normalized] = StrategyGovernance(
            name=normalized,
            version=version,
            enabled=enabled,
            rollout_pct=max(0, min(100, int(rollout_pct))),
            supported_regimes=supported_regimes or self._default_supported_regimes(normalized),
        )
        self._audit("registered", normalized, self._governance[normalized].to_dict())

    def available(self) -> list[str]:
        return sorted(name for name in self._strategies if self._governance.get(name, StrategyGovernance(name)).enabled)

    def registry(self) -> list[dict[str, Any]]:
        return [self._governance[name].to_dict() for name in sorted(self._strategies)]

    def audit_trail(self) -> list[dict[str, Any]]:
        return list(self._audit_trail)

    def configure_strategy(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        rollout_pct: int | None = None,
        version: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize(name)
        if normalized not in self._strategies:
            raise ValueError(f"Unknown strategy '{name}'. Available: {', '.join(sorted(self._strategies))}")
        current = self._governance[normalized]
        if enabled is not None:
            current.enabled = bool(enabled)
        if rollout_pct is not None:
            current.rollout_pct = max(0, min(100, int(rollout_pct)))
        if version is not None:
            current.version = str(version)
        if notes is not None:
            current.notes = str(notes)
        current.updated_at = datetime.now(timezone.utc).isoformat()
        self._audit("configured", normalized, current.to_dict())
        return current.to_dict()

    def run(self, strategy_name: str, data: Any, context: StrategyContext) -> list[StrategySignal]:
        strategy = self._strategies.get(self._normalize(strategy_name))
        if strategy is None:
            raise ValueError(f"Unknown strategy '{strategy_name}'. Available: {', '.join(self.available())}")
        governance = self._governance.get(self._normalize(strategy_name))
        if governance and (not governance.enabled or governance.rollout_pct <= 0):
            self._audit("blocked", self._normalize(strategy_name), governance.to_dict())
            raise ValueError(f"Strategy '{strategy_name}' is disabled by governance.")
        return strategy.run(data, context)

    def run_many(self, strategy_names: list[str], data: Any, context: StrategyContext) -> dict[str, list[StrategySignal]]:
        return {name: self.run(name, data, context) for name in strategy_names}

    def _normalize(self, name: str) -> str:
        return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")

    @staticmethod
    def _default_supported_regimes(name: str) -> list[str]:
        mapping = {
            "breakout": ["Trending", "Gap Up", "Gap Down"],
            "amd": ["Trending", "Range"],
            "mean_reversion": ["Range", "Low Volatility", "Holiday Effect"],
            "supply_demand": ["Trending", "Range", "Gap Up", "Gap Down"],
            "mtf": ["Trending"],
            "mtfa": ["Trending"],
            "btst": ["Trending", "Expiry Day"],
            "cbt": ["Range", "Volatile"],
            "crt_tbs": ["Range", "Volatile"],
        }
        return mapping.get(name, ["Any"])

    def _audit(self, event: str, strategy: str, details: dict[str, Any]) -> None:
        self._audit_trail.append(
            {
                "event": event,
                "strategy": strategy,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
