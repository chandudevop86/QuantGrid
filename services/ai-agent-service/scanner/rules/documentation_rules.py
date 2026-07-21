from pathlib import Path


def check_documentation(file_path):

    findings = []

    path = Path(file_path)

    name = path.name.lower()

    # README
    if name == "readme.md":
        return findings

    # Python files
    if path.suffix == ".py":

        try:
            code = path.read_text(errors="ignore")
        except Exception:
            return findings

        if '"""' not in code and "'''" not in code:

            findings.append({
                "id": "DOC-001",
                "severity": "LOW",
                "issue": "Missing module docstring",
                "file": file_path,
            })

        if "TODO" in code:

            findings.append({
                "id": "DOC-002",
                "severity": "LOW",
                "issue": "TODO comments present",
                "file": file_path,
            })

        if "FIXME" in code:

            findings.append({
                "id": "DOC-003",
                "severity": "MEDIUM",
                "issue": "FIXME comments present",
                "file": file_path,
            })

        if "# " not in code:

            findings.append({
                "id": "DOC-004",
                "severity": "LOW",
                "issue": "Very few code comments",
                "file": file_path,
            })

    return findings