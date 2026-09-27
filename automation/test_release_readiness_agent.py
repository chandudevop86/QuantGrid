import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_readiness_agent import build_release_checklist, load_report


class ReleaseReadinessAgentTests(unittest.TestCase):
    def test_green_executed_checks_are_ready_for_human_review(self):
        report = {
            "mode": "verification-only",
            "healthy": True,
            "checks": [
                {"check": "automation-tests", "executed": True, "returncode": 0},
                {"check": "git-diff-check", "executed": True, "returncode": 0},
            ],
        }

        result = build_release_checklist(report)

        self.assertTrue(result["ready_for_human_review"])
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["safety"]["merges"])
        self.assertFalse(result["safety"]["deploys"])
        self.assertFalse(result["safety"]["live_trading"])

    def test_dry_run_verification_is_not_release_ready(self):
        report = {
            "mode": "verification-only",
            "healthy": True,
            "checks": [
                {"check": "automation-tests", "executed": False, "returncode": None},
            ],
        }

        result = build_release_checklist(report)

        self.assertFalse(result["ready_for_human_review"])
        self.assertIn("automation-tests", result["blockers"][0])

    def test_failed_check_is_a_blocker(self):
        report = {
            "mode": "verification-only",
            "healthy": False,
            "checks": [
                {"check": "automation-tests", "executed": True, "returncode": 1},
            ],
        }

        result = build_release_checklist(report)

        self.assertFalse(result["ready_for_human_review"])
        self.assertTrue(any("failed" in blocker.lower() for blocker in result["blockers"]))

    def test_non_verification_report_is_rejected(self):
        with self.assertRaises(ValueError):
            build_release_checklist({"mode": "deployment", "checks": [{}]})

    def test_load_report_reads_small_json_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "mode": "verification-only",
                        "healthy": True,
                        "checks": [
                            {
                                "check": "automation-tests",
                                "executed": True,
                                "returncode": 0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = load_report(path)

        self.assertEqual(result["mode"], "verification-only")


if __name__ == "__main__":
    unittest.main()
