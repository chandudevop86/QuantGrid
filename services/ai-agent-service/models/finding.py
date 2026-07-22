from dataclasses import dataclass, field

from models.evidence import Evidence
from models.risk import RiskScore
from models.enums import Severity, Category

@dataclass(slots=True)
class Finding:
    id: str
    title: str
    severity: Severity
    category: Category
    description: str
    recommendation: str
    file: str
    line: int
    confidence: float = 1.0

    cwe: str | None = None
    owasp: str | None = None
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    evidence: list[Evidence] = field(default_factory=list)