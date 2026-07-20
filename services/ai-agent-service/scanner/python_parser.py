import ast


def analyze_python_file(file):

    findings=[]


    try:

        with open(file) as f:
            code=f.read()


        tree=ast.parse(code)


        for node in ast.walk(tree):

            if isinstance(node,ast.Import):

                pass


            if isinstance(node,ast.Try):

                findings.append(
                    {
                    "type":"exception_block",
                    "file":file
                    }
                )


    except Exception as e:

        findings.append(
            {
            "error":str(e),
            "file":file
            }
        )


    return findings