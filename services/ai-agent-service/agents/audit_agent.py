from scanner.repo_scanner import scan_repository
from scanner.python_parser import analyze_python_file

from agents.architecture_agent import analyze_architecture
from agents.security_agent import analyze_security


def run_audit(path):

    files = scan_repository(path)

    findings = []

    # Code analysis
    for file in files:

        if file.endswith(".py"):

            result = analyze_python_file(file)
            findings.extend(result)

    # Security analysis (run once)
    security = analyze_security(path)

    findings.extend(
        security["findings"]
    )

    # Architecture analysis (run once)
    architecture = analyze_architecture(path)

    # Build report
    report = {
        "files_scanned": len(files),
        "findings": findings,
        "architecture": architecture,
        "security": security,
    }

    return report