import ast

from scanner.rules.security_rules import check_security
from scanner.rules.code_quality_rules import check_quality
from scanner.rules.trading_rules import check_trading



def analyze_python_file(file):

    findings=[]


    try:

        with open(
            file,
            errors="ignore"
        ) as f:

            code=f.read()


        tree=ast.parse(code)


        findings.extend(
            check_security(
                file,
                code
            )
        )


        findings.extend(
            check_quality(
                file,
                tree
            )
        )


        findings.extend(
            check_trading(
                file,
                code
            )
        )


    except Exception as e:

        findings.append(
            {
            "id":"PARSER-001",
            "severity":"LOW",
            "issue":str(e),
            "file":file
            }
        )


    return findings