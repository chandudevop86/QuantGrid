from scanner.repo_scanner import scan_repository
from scanner.rules.documentation_rules import check_documentation


def analyze_documentation(path: str):

    findings = []

    files = scan_repository(path)

    for file in files:
        findings.extend(check_documentation(file))

    return {
        "agent": "Documentation Agent",
        "score": calculate_documentation_score(findings),
        "findings": findings,
    }


def calculate_documentation_score(findings):

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