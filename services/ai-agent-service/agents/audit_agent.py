from scanner.repo_scanner import scan_repository
from scanner.python_parser import analyze_python_file

from agents.architecture_agent import analyze_architecture
from agents.security_agent import analyze_security


def run_audit(path: str):

    files = scan_repository(path)

    findings = []

    # -----------------------------
    # Code Analysis
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
                    "id": "AUDIT-ERROR",
                    "severity": "LOW",
                    "issue": f"Code analysis failed: {e}",
                    "file": file,
                }
            )

    # -----------------------------
    # Security Analysis
    # -----------------------------
    try:
        security = analyze_security(path)
        findings.extend(
            security.get("findings", [])
        )
    except Exception as e:
        security = {
            "agent": "Security Agent",
            "score": 0,
            "findings": [],
            "error": str(e),
        }

    # -----------------------------
    # Architecture Analysis
    # -----------------------------
    try:
        architecture = analyze_architecture(path)
    except Exception as e:
        architecture = {
            "agent": "Architecture Agent",
            "score": 0,
            "services": [],
            "technologies": [],
            "warnings": [],
            "recommendations": [],
            "error": str(e),
        }

    # -----------------------------
    # Final Report
    # -----------------------------
    return {
        "files_scanned": len(files),
        "findings": findings,
        "architecture": architecture,
        "security": security,
    }