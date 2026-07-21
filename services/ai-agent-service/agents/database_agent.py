from scanner.repo_scanner import scan_repository
from scanner.rules.database_rules import check_database


def analyze_database(path: str):

    findings = []

    files = scan_repository(path)

    for file in files:

        if not file.endswith(".py"):
            continue

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()

            findings.extend(
                check_database(file, code)
            )

        except Exception:
            pass

    return {
        "agent": "Database Agent",
        "score": calculate_database_score(findings),
        "findings": findings,
    }


def calculate_database_score(findings):

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