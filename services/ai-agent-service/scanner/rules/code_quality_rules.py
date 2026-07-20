import ast


def check_quality(file_path, tree):

    findings=[]


    for node in ast.walk(tree):

        if isinstance(node, ast.ExceptHandler):

            if node.type is None:

                findings.append(
                    {
                    "id":"CODE-001",
                    "severity":"MEDIUM",
                    "issue":"Bare except detected",
                    "file":file_path
                    }
                )


    return findings