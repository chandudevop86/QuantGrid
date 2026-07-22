from dataclasses import dataclass

@dataclass(slots=True)
class Evidence:
    file: str
    line: int
    snippet: str
    reason: str