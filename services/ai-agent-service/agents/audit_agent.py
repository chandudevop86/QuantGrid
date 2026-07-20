from scanner.repo_scanner import scan_repository
from scanner.python_parser import analyze_python_file



def run_audit(path):


    files = scan_repository(path)


    report=[]


    for file in files:


        if file.endswith(".py"):

            result = analyze_python_file(file)

            report.extend(result)



    return {

        "files_scanned":len(files),

        "findings":report

    }