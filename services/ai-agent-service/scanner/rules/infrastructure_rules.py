import os


def check_infrastructure(file_path, code):

    findings = []

    name = os.path.basename(file_path).lower()

    # -------------------------
    # Docker
    # -------------------------

    if name == "dockerfile":

        if "healthcheck" not in code.lower():

            findings.append({
                "id": "INFRA-001",
                "severity": "MEDIUM",
                "issue": "Docker HEALTHCHECK missing",
                "file": file_path,
            })

    # -------------------------
    # Docker Compose
    # -------------------------

    if "docker-compose" in name or name.endswith(".yml"):

        if "restart:" not in code:

            findings.append({
                "id": "INFRA-002",
                "severity": "LOW",
                "issue": "Container restart policy missing",
                "file": file_path,
            })

    # -------------------------
    # Terraform
    # -------------------------

    if file_path.endswith(".tf"):

        if "versioning" not in code.lower():

            findings.append({
                "id": "INFRA-003",
                "severity": "MEDIUM",
                "issue": "S3 Versioning not detected",
                "file": file_path,
            })

        if "encrypt" not in code.lower():

            findings.append({
                "id": "INFRA-004",
                "severity": "HIGH",
                "issue": "Storage encryption not detected",
                "file": file_path,
            })

    # -------------------------
    # Kubernetes
    # -------------------------

    if "deployment" in name:

        if "livenessprobe" not in code.lower():

            findings.append({
                "id": "INFRA-005",
                "severity": "MEDIUM",
                "issue": "Kubernetes Liveness Probe missing",
                "file": file_path,
            })

        if "readinessprobe" not in code.lower():

            findings.append({
                "id": "INFRA-006",
                "severity": "MEDIUM",
                "issue": "Kubernetes Readiness Probe missing",
                "file": file_path,
            })

    return findings