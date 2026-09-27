import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verification_agent import DEFAULT_CHECKS, verify


class VerificationAgentTests(unittest.TestCase):
    @patch("verification_agent.run_check")
    def test_default_bundle_is_dry_run(self, run_check):
        run_check.side_effect = [
            {
                "check": "automation-tests",
                "executed": False,
                "returncode": None,
            },
            {
                "check": "git-diff-check",
                "executed": False,
                "returncode": None,
            },
        ]

        result = verify()

        self.assertTrue(result["healthy"])
        self.assertFalse(result["executed"])
        self.assertEqual(tuple(DEFAULT_CHECKS), ("automation-tests", "git-diff-check"))
        self.assertEqual(
            [call.args[0] for call in run_check.call_args_list],
            ["automation-tests", "git-diff-check"],
        )
        self.assertTrue(
            all(call.kwargs["execute"] is False for call in run_check.call_args_list)
        )

    @patch("verification_agent.run_check")
    def test_execute_reports_failed_allow_listed_check(self, run_check):
        run_check.side_effect = [
            {
                "check": "automation-tests",
                "executed": True,
                "returncode": 1,
            },
            {
                "check": "git-diff-check",
                "executed": True,
                "returncode": 0,
            },
        ]

        result = verify(execute=True)

        self.assertFalse(result["healthy"])
        self.assertEqual(result["failed_checks"], ["automation-tests"])
        self.assertFalse(result["safety"]["places_orders"])
        self.assertFalse(result["safety"]["deploys"])

    def test_unknown_check_is_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            verify(["deploy-production"], execute=True)

    def test_empty_check_list_is_rejected(self):
        with self.assertRaises(ValueError):
            verify([], execute=True)


if __name__ == "__main__":
    unittest.main()
