"""Read-only agent task planner. No API calls, shell commands, or code execution."""
import argparse
import json
from pathlib import Path

PROJECTS = {"quantgrid", "foodtruck"}
ROLES = {"coordinator", "implementation", "verification", "release"}


def plan(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or set(manifest) != {"project", "task", "checks"}:
        raise ValueError("Expected exactly project, task, checks")
    project, task, checks = manifest["project"], manifest["task"], manifest["checks"]
    if project not in PROJECTS or not isinstance(task, str) or not 1 <= len(task.strip()) <= 200:
        raise ValueError("Invalid project or task")
    if not isinstance(checks, list) or not checks or len(checks) > 20 or any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 120 for x in checks):
        raise ValueError("checks must contain 1-20 short descriptions")
    return {"project": project, "task": task.strip(), "stages": [
        {"role": "coordinator", "action": "Scope task and acceptance criteria"},
        {"role": "implementation", "action": "Propose changes on an isolated branch"},
        {"role": "verification", "action": "Report actual results for requested checks", "checks": checks},
        {"role": "release", "action": "Prepare human-reviewed release checklist only"},
    ], "execution": "planning-only", "requires_human_approval": ["merge", "production deployment", "live trading", "payment changes"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    # Limit input size and do not interpret manifest fields as commands.
    if args.manifest.stat().st_size > 16384:
        parser.error("Manifest too large")
    try:
        result = plan(json.loads(args.manifest.read_text(encoding="utf-8")))
    except (ValueError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
