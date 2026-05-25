from __future__ import annotations

import json
from pathlib import Path


def ensure_dashboard_job_store() -> Path:
    data_dir = Path("services/trading-service/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    jobs_file = data_dir / "dashboard_jobs.json"

    if not jobs_file.exists():
        jobs_file.write_text("{}", encoding="utf-8")

    json.loads(jobs_file.read_text(encoding="utf-8"))
    return jobs_file


def main() -> None:
    jobs_file = ensure_dashboard_job_store()
    print(f"Dashboard job store ready: {jobs_file}")


if __name__ == "__main__":
    main()
