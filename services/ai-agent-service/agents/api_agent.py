from scanner.repo_scanner import scan_repository
from scanner.rules.api_rules import check_api


def analyze_api(path: str):

    findings = []

    files = scan_repository(path)

    for file in files:

        if not file.endswith(".py"):
            continue

        findings.extend(check_api(file))

    return {
        "agent": "API Agent",
        "score": calculate_api_score(findings),
        "findings": findings,
    }


def calculate_api_score(findings):

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