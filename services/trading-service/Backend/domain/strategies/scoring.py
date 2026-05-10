from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScoreBreakdown:
    components: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return float(sum(self.components.values()))

    def add(self, name: str, value: float, enabled: bool = True) -> None:
        if enabled:
            self.components[name] = float(value)


class ScoringEngine:
    def threshold(self, mode: str, *, conservative: float, balanced: float, aggressive: float) -> float:
        normalized = str(mode or "").strip().lower()
        if normalized == "conservative":
            return float(conservative)
        if normalized == "aggressive":
            return float(aggressive)
        return float(balanced)

    def passed(self, score: float, threshold: float) -> bool:
        return float(score) >= float(threshold)
