from scanner.repo_scanner import scan_repository
from scanner.python_parser import analyze_python_file
from agents.architecture_agent import analyze_architecture
from agents.security_agent import analyze_security

def run_audit(path):

    files = scan_repository(path)

    findings = []


    for file in files:

        if file.endswith(".py"):

            result = analyze_python_file(file)

            findings.extend(result)
        security = analyze_security(path)

        report["security"] = security

        report["findings"].extend(
        security["findings"]
    )

    architecture = analyze_architecture(path)
    

    return {

        "files_scanned": len(files),

        "findings": findings,

        "architecture": architecture

    }
    