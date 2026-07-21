from scanner.repo_scanner import scan_repository
from scanner.rules.trading_rules import check_trading


def analyze_trading(path: str):
    """
    Scan the repository for trading-specific risks.
    """

    findings = []

    files = scan_repository(path)

    for file in files:

        if file.endswith(".py"):

            findings.extend(
                check_trading(file)
            )

    return {
        "agent": "Trading Agent",
        "score": calculate_trading_score(findings),
        "findings": findings,
    }


def calculate_trading_score(findings):

    score = 100

    for finding in findings:

        severity = finding.get("severity", "LOW")

        if severity == "HIGH":
            score -= 15

        elif severity == "MEDIUM":
            score -= 8

        elif severity == "LOW":
            score -= 3

    return max(score, 0)