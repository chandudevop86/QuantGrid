from pathlib import Path


def analyze_architecture(path):

    root = Path(path)

    report = {
        "agent": "Architecture Agent",
        "score": 100,
        "services": [],
        "technologies": [],
        "warnings": [],
        "recommendations": []
    }


    # Detect services

    services_dir = root / "services"

    if services_dir.exists():

        for item in services_dir.iterdir():

            if item.is_dir():

                report["services"].append(
                    item.name
                )


    # Technology detection

    files = list(
        root.rglob("*")
    )


    for file in files:

        if file.name == "Dockerfile":

            report["technologies"].append(
                "Docker"
            )


        if file.name in [
            "requirements.txt",
            "pyproject.toml"
        ]:

            report["technologies"].append(
                "Python"
            )


        if file.name == "package.json":

            report["technologies"].append(
                "Node.js"
            )


        if file.suffix == ".tf":

            report["technologies"].append(
                "Terraform"
            )


    report["technologies"] = list(
        set(report["technologies"])
    )


    # Architecture checks


    if "Docker" not in report["technologies"]:

        report["score"] -= 10

        report["warnings"].append(
            "Docker containerization not detected"
        )


    if "Terraform" not in report["technologies"]:

        report["score"] -= 10

        report["warnings"].append(
            "Infrastructure as Code not detected"
        )


    if len(report["services"]) == 0:

        report["score"] -= 15

        report["warnings"].append(
            "No service separation detected"
        )


    # Recommendations

    if report["score"] < 100:

        report["recommendations"].extend(
            [
                "Add centralized logging",
                "Add service health checks",
                "Implement distributed tracing",
                "Add infrastructure monitoring"
            ]
        )


    return report