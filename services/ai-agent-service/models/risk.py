from dataclasses import dataclass

@dataclass(slots=True)
class RiskScore:
    impact: int
    likelihood: int
    exploitability: int
    confidence: float

    @property
    def score(self) -> float:
        return (
            self.impact +
            self.likelihood +
            self.exploitability
        ) / 3 * self.confidence