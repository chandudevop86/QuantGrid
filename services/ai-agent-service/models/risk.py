from dataclasses import dataclass

from models.enums import Severity
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

def risk_score(severity: Severity) -> int:
    return {
        Severity.CRITICAL: 10,
        Severity.HIGH: 8,
        Severity.MEDIUM: 5,
        Severity.LOW: 2,
        Severity.INFO: 1,
    }[severity]