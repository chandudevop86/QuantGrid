from dataclasses import dataclass, field

from models.evidence import Evidence
from models.risk import RiskScore

@dataclass(slots=True)
class Finding:
    id: str
    title: str
    severity: str
    category: str

    description: str
    recommendation: str

    file: str
    line: int

    confidence: float

    standards: list[str] = field(default_factory=list)

    evidence: list[Evidence] = field(default_factory=list)

    risk: RiskScore | None = None