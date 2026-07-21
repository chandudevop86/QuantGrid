from pathlib import Path
import re


def check_testing(file_path):

    findings = []

    try:
        code = Path(file_path).read_text(errors="ignore")
    except Exception:
        return findings

    if "pytest" not in code and "unittest" not in code:
        findings.append({
            "id": "TEST-001",
            "severity": "HIGH",
            "issue": "No test framework detected",
            "file": file_path,
        })

    if "assert" not in code:
        findings.append({
            "id": "TEST-002",
            "severity": "MEDIUM",
            "issue": "No assertions detected",
            "file": file_path,
        })

    if re.search(r"mock|patch|MagicMock", code, re.IGNORECASE) is None:
        findings.append({
            "id": "TEST-003",
            "severity": "LOW",
            "issue": "No mocking detected",
            "file": file_path,
        })

    if "pytest.mark" not in code:
        findings.append({
            "id": "TEST-004",
            "severity": "LOW",
            "issue": "No pytest markers found",
            "file": file_path,
        })

    return findings
