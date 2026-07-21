from scanner.repo_scanner import scan_repository
from scanner.rules.security_rules import check_security


def analyze_security(path: str):

    findings = []

    files = scan_repository(path)

    for file in files:
        if file.endswith(".py"):
            findings.extend(check_security(file))

    return {
        "agent": "Security Agent",
        "score": calculate_security_score(findings),
        "findings": findings,
    }


def calculate_security_score(findings):

    score = 100

    for finding in findings:

        severity = finding.get("severity")

        if severity == "HIGH":
            score -= 10

        elif severity == "MEDIUM":
            score -= 5

        elif severity == "LOW":
            score -= 2

    return max(score, 0)