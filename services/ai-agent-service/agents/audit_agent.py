
from scanner.python_parser import analyze_python_file
from agents.architecture_agent import analyze_architecture
from agents.security_agent import analyze_security
from agents.performance_agent import analyze_performance
from agents.database_agent import analyze_database
from agents.devops_agent import analyze_devops
from agents.api_agent import analyze_api
from agents.testing_agent import analyze_testing
from agents.documentation_agent import analyze_documentation
from agents.infrastructure_agent import analyze_infrastructure
from scanner.scan_context import ScanContext
from collections import Counter
from scanner.finding_normalizer import deduplicate_findings
from scanner.confidence import enrich_confidence
from scanner.risk_filter import filter_actionable_findings
def safe_run(agent, path, name):
    try:
        return agent(path)
    except Exception as e:
        return {
            "agent": name,
            "score": 0,
            "findings": [],
            "error": str(e)
        }


def run_audit(path: str):

    context = ScanContext(path)

    files = context.files

    findings = []

    # -----------------------------
    # Python Code Analysis
    # -----------------------------
    for file in files:

        if not file.endswith(".py"):
            continue

        try:
            findings.extend(
                analyze_python_file(file)
            )

        except Exception as e:
            findings.append(
                {
                    "id": "CODE-ERROR",
                    "severity": "LOW",
                    "issue": str(e),
                    "file": file
                }
            )


    # -----------------------------
    # Specialized Agents
    # -----------------------------

    security = safe_run(
    analyze_security,
    context,
    "Security Agent"
    )

    performance = safe_run(
        analyze_performance,
        path,
        "Performance Agent"
    )

    database = safe_run(
        analyze_database,
        path,
        "Database Agent"
    )

    architecture = safe_run(
        analyze_architecture,
        path,
        "Architecture Agent"
    )

    devops = safe_run(
        analyze_devops,
        path,
        "DevOps Agent"
    )

    api = safe_run(
        analyze_api,
        path,
        "API Agent"
    )

    testing = safe_run(
        analyze_testing,
        path,
        "Testing Agent"
    )

    documentation = safe_run(
        analyze_documentation,
        path,
        "Documentation Agent"
    )

    infrastructure = safe_run(
        analyze_infrastructure,
        path,
        "Infrastructure Agent"
    )


    # -----------------------------
    # Findings Aggregation
    # -----------------------------

    agents = [
        security,
        performance,
        database,
        architecture,
        devops,
        api,
        testing,
        documentation,
        infrastructure,
    ]


    for agent in agents:
        findings.extend(
            agent.get("findings", [])
        )

    findings = deduplicate_findings(findings)
    findings = enrich_confidence(findings)
    findings = filter_actionable_findings(findings) 
    severity_summary = Counter(
    f.get("severity", "UNKNOWN").upper()
    for f in findings
)
    # -----------------------------
    # Final Audit Result
    # -----------------------------

    return {

        "files_scanned": len(files),

        "findings": findings,

        "architecture": architecture,

        "security": security,

        "performance": performance,

        "database": database,

        "devops": devops,

        "api": api,

        "testing": testing,

        "documentation": documentation,

        "infrastructure": infrastructure,
        "summary": {
                "critical": severity_summary["CRITICAL"],
                "high": severity_summary["HIGH"],
                "medium": severity_summary["MEDIUM"],
                "low": severity_summary["LOW"],
                "total": len(findings)
        },

    }