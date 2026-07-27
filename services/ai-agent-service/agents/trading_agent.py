from scanner.repo_scanner import scan_repository
from scanner.rules.trading_rules import check_trading

from app.llm.openai_client import ask_llm


def analyze_trading(path: str):

    """
    AI Trading Agent:
    - scans trading code
    - calculates risk
    - explains findings using LLM
    """

    findings = []

    files = scan_repository(path)

    for file in files:

        if file.endswith(".py"):

            findings.extend(
                check_trading(file)
            )


    score = calculate_trading_score(findings)


    ai_analysis = explain_trading_risk(
        findings,
        score
    )


    return {

        "agent":
            "AI Trading Agent",

        "score":
            score,

        "findings":
            findings,

        "llm_analysis":
            ai_analysis
    }



def calculate_trading_score(findings):

    score = 100

    for finding in findings:

        severity = finding.get(
            "severity",
            "LOW"
        )


        if severity == "CRITICAL":
            score -= 25

        elif severity == "HIGH":
            score -= 15

        elif severity == "MEDIUM":
            score -= 8

        elif severity == "LOW":
            score -= 3


    return max(score, 0)



def explain_trading_risk(
        findings,
        score
):

    prompt = f"""

You are QuantGrid AI Trading Auditor.

Analyze this algorithmic trading code audit.

Trading Risk Score:
{score}/100


Findings:

{findings}


Provide:

1. Trading system health
2. Strategy risks
3. Execution risks
4. Risk management issues
5. Market data issues
6. Recommended fixes
7. Production readiness rating


Focus on:
- signal quality
- entry/exit logic
- stop loss handling
- position sizing
- backtesting
- slippage
- latency
- broker execution safety

"""


    return ask_llm(prompt)