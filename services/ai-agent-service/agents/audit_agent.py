from scanner.repo_scanner import scan_repository
from scanner.python_parser import analyze_python_file

from agents.architecture_agent import analyze_architecture
from agents.security_agent import analyze_security
from agents.performance_agent import analyze_performance
from agents.database_agent import analyze_databasefrom 
from agents.devops_agent import analyze_devops
from agents.api_agent import analyze_api




def run_audit(path: str):

    files = scan_repository(path)

    findings = []

    # ------------------------------------
    # Code Analysis
    # ------------------------------------
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

    # ------------------------------------
    # Security Analysis
    # ------------------------------------
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

    # ------------------------------------
    # Performance Analysis
    # ------------------------------------
    try:

        performance = analyze_performance(path)

        findings.extend(
            performance.get("findings", [])
        )

    except Exception as e:

        performance = {
            "agent": "Performance Agent",
            "score": 0,
            "findings": [],
            "error": str(e),
        }
        
    database = analyze_database(path)

    findings.extend(
    database.get("findings", [])
)    

    content += f"""

---

# Database Assessment

Database Score:
{database_score}/100

Agent:
{database.get("agent", "")}

Database Findings:
{len(database.get("findings", []))}

"""
    # ------------------------------------
    # Architecture Analysis
    # ------------------------------------
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
        
        devops = analyze_devops(path)

        findings.extend(
        devops["findings"]
    )
        
        api = analyze_api(path)
        findings.extend(api["findings"])
        

    # ------------------------------------
    # Final Report
    # ------------------------------------
    return {
        "files_scanned": len(files),
        "findings": findings,
        "architecture": architecture,
        "security": security,
        "performance": performance,
        "database": database,
        "devops": devops,
        "api": api,
    }