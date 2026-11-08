"""Regression checks for the cross-step CI report handoff."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci-bottleneck-agent.yml"
SCRIPT = ROOT / "scripts/ci_bottleneck_agent.py"


def test_bottleneck_report_shared_between_steps():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert workflow.count("QUANTGRID_CI_REPORT_PATH:") == 2
    assert "const summaryPath = process.env.QUANTGRID_CI_REPORT_PATH;" in workflow
    assert "const body = fs.readFileSync(summaryPath, 'utf8');" in workflow


def test_bottleneck_report_contains_marker_in_shared_file(tmp_path):
    report_path = tmp_path / "report.md"
    summary_path = tmp_path / "summary.md"
    code = (
        "import scripts.ci_bottleneck_agent as agent; "
        "agent.collect = lambda: {'runs_analyzed': 0, 'jobs': [], 'stale_prs': []}; "
        "agent.main()"
    )
    env = dict(os.environ, QUANTGRID_CI_REPORT_PATH=str(report_path),
               GITHUB_STEP_SUMMARY=str(summary_path))
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    marker = "<!-- quantgrid-bottleneck-agent -->"
    assert marker in report_path.read_text(encoding="utf-8")
    assert marker in summary_path.read_text(encoding="utf-8")
