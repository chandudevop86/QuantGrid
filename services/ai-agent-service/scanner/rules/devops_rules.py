from pathlib import Path

REQUIRED_FILES = {

    "Dockerfile": (
        "DEVOPS-001",
        "HIGH",
        "Dockerfile missing"
    ),

    "docker-compose.yml": (
        "DEVOPS-002",
        "MEDIUM",
        "Docker Compose missing"
    ),

    ".github/workflows": (
        "DEVOPS-003",
        "MEDIUM",
        "GitHub Actions missing"
    ),

    "terraform": (
        "DEVOPS-004",
        "LOW",
        "Terraform directory missing"
    ),

    "helm": (
        "DEVOPS-005",
        "LOW",
        "Helm charts missing"
    ),

    "monitoring": (
        "DEVOPS-006",
        "LOW",
        "Monitoring configuration missing"
    ),

    "k8s": (
        "DEVOPS-007",
        "LOW",
        "Kubernetes manifests missing"
    ),
}


def check_devops(file_path):

    findings = []

    root = Path(file_path)

    while root.parent != root:
        root = root.parent

    for target, rule in REQUIRED_FILES.items():

        if not (root / target).exists():

            findings.append({
                "id": rule[0],
                "severity": rule[1],
                "issue": rule[2],
                "file": str(root),
            })

    return findings