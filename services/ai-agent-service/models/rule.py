from dataclasses import dataclass

@dataclass(slots=True)
class Rule:
    id: str
    title: str
    description: str
    severity: str
    category: str
    standards: list[str]
    references: list[str]