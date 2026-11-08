#!/usr/bin/env python3
"""Analyze GitHub Actions run timings and PR queue without changing production."""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
REPORT_MARKER = "<!-- quantgrid-bottleneck-agent -->"


def get(path: str):
    request = urllib.request.Request(
        API + path,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "quantgrid-bottleneck-agent"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def seconds(start, end):
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0, (b - a).total_seconds())
    except (TypeError, ValueError):
        return None


def collect():
    if not REPO or not TOKEN:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    runs = get(f"/repos/{REPO}/actions/workflows/ci.yml/runs?per_page=20&status=completed").get("workflow_runs", [])
    by_job = {}
    for run in runs:
        jobs = get(f"/repos/{REPO}/actions/runs/{run['id']}/jobs?per_page=100").get("jobs", [])
        for job in jobs:
            duration = seconds(job.get("started_at"), job.get("completed_at"))
            if duration is None:
                continue
            item = by_job.setdefault(job["name"], {"durations": [], "failures": 0, "samples": 0})
            item["durations"].append(duration)
            item["samples"] += 1
            item["failures"] += job.get("conclusion") == "failure"
    pulls = get(f"/repos/{REPO}/pulls?state=open&per_page=100").copy()
    now = datetime.now(timezone.utc)
    stale = []
    for pr in pulls:
        updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        age = (now - updated).days
        if age >= 3:
            stale.append({"number": pr["number"], "age_days": age, "draft": pr["draft"]})
    metrics = [
        {"job": name, "median_seconds": round(statistics.median(data["durations"]), 1),
         "max_seconds": round(max(data["durations"]), 1),
         "failures": data["failures"], "samples": data["samples"]}
        for name, data in by_job.items()
    ]
    metrics.sort(key=lambda row: row["median_seconds"], reverse=True)
    return {"runs_analyzed": len(runs), "jobs": metrics, "stale_prs": stale}


def markdown(report):
    lines = [REPORT_MARKER, "# QuantGrid CI and development bottlenecks",
             f"Completed CI runs analyzed: **{report['runs_analyzed']}**.",
             "", "| CI job | Median duration | Max duration | Failures / samples |",
             "|---|---:|---:|---:|"]
    for job in report["jobs"]:
        lines.append(f"| {job['job'].replace('|', '/')} | {job['median_seconds']:.0f}s | {job['max_seconds']:.0f}s | {job['failures']} / {job['samples']} |")
    lines.extend(["", "## Automated findings"])
    if not report["jobs"]:
        lines.append("- No completed CI jobs were available; no performance conclusions can be drawn.")
    else:
        slowest = report["jobs"][0]
        lines.append(f"- Longest median CI job: **{slowest['job']}** ({slowest['median_seconds']:.0f}s).")
        lines.append("- Investigate long test groups and cache misses before increasing timeouts.")
        for job in report["jobs"]:
            if job["failures"]:
                lines.append(f"- Reliability: **{job['job']}** failed {job['failures']} of {job['samples']} sampled runs.")
    lines.append(f"- Open PRs untouched for 3+ days: **{len(report['stale_prs'])}**.")
    for pr in report["stale_prs"][:20]:
        lines.append(f"  - PR #{pr['number']}: {pr['age_days']} days since update{' (draft)' if pr['draft'] else ''}")
    lines.extend(["", "## Suggested next actions",
                  "1. Profile the slowest CI job and identify its slowest steps or tests.",
                  "2. Split or parallelize test groups only after preserving coverage aggregation.",
                  "3. Fix repeatedly failing checks before merging dependent PRs.",
                  "4. Review stale stacked PRs and close or rebase obsolete branches.",
                  "", "_Read-only diagnostics. No code, risk limits, broker settings or deployments are changed._"])
    return "\n".join(lines)


def main():
    report = collect()
    output = markdown(report)
    print(output)
    report_path = os.environ.get("QUANTGRID_CI_REPORT_PATH")
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(output + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write("report_ready=true\n")


if __name__ == "__main__":
    main()
