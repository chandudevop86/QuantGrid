from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_client_handover_package_covers_required_acceptance_artifacts():
    required = {
        "client-handover.md": ("paper mode", "UAT", "rollback", "backup"),
        "uat-acceptance-template.md": ("Direct URL", "Known limitations", "Signatures"),
        "known-limitations.md": ("Billing", "Live trading", "RPO/RTO"),
        "release-evidence-template.md": ("Bandit", "Compose", "Do not paste tokens"),
        "backup-and-restore.md": ("ALLOW_DATABASE_RESTORE", "RPO 24 hours", "restore drill"),
    }
    for filename, phrases in required.items():
        content = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        for phrase in phrases:
            assert phrase.lower() in content.lower(), f"{filename} is missing {phrase!r}"
