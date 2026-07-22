from dataclasses import dataclass, field

from models.finding import Finding

@dataclass(slots=True)
class AuditReport:

    project: str

    version: str

    findings: list[Finding] = field(default_factory=list)

    scan_time: float = 0

    files_scanned: int = 0

    total_lines: int = 0

    @property
    def critical(self):
        return sum(
            1
            for f in self.findings
            if f.severity == "Critical"
        )

    @property
    def high(self):
        return sum(
            1
            for f in self.findings
            if f.severity == "High"
        )