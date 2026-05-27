from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "node_modules", "dist", "__pycache__", ".pytest_cache", "experimental", "tests"}
ALLOW_FILES = {
    Path("scripts/check_production_config.py"),
    Path("scripts/check_no_secrets.py"),
}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".sh",
    ".service",
    ".conf",
    ".toml",
    ".txt",
}

PATTERNS = [
    re.compile(r"(username|user)\s*[:=]\s*['\"]?admin['\"]?.{0,40}(password|pass)\s*[:=]\s*['\"]?admin123", re.IGNORECASE),
    re.compile(r"(password|pass)\s*[:=]\s*['\"]?(admin123|password123)['\"]?", re.IGNORECASE),
    re.compile(r"QUANTGRID_AUTH_SECRET\s*=\s*(?:changeme|secret|password)", re.IGNORECASE),
    re.compile(r"(api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]", re.IGNORECASE),
]


def should_scan(path: Path, root: Path = ROOT) -> bool:
    relative = path.relative_to(root)
    if relative in ALLOW_FILES:
        return False
    if any(part in SKIP_PARTS for part in relative.parts):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Jenkinsfile", "VERSION", "CODEOWNERS"}


def find_secrets(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or not should_scan(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                findings.append(str(path.relative_to(root)))
                break
    return findings


def main() -> int:
    findings = find_secrets()

    if findings:
        print("Potential secrets/default credentials detected:")
        for finding in findings:
            print(f" - {finding}")
        return 1
    print("No obvious secrets or default credentials detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
