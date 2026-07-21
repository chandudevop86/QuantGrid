from scanner.repo_scanner import scan_repository
from scanner.python_parser import analyze_python_file
from agents.architecture_agent import analyze_architecture


def run_audit(path):


    files = scan_repository(path)


    report=[]


    for file in files:


        if file.endswith(".py"):

            result = analyze_python_file(file)

            report.extend(result)
    architecture = analyze_architecture(path)

    report["architecture"] = architecture


    return {

        "files_scanned":len(files),

        "findings":report

    }