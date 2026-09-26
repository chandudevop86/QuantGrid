import unittest
from unittest.mock import patch

from agent_runner import SAFE_CHECKS, run_check


class AgentRunnerTests(unittest.TestCase):
    def test_dry_run_does_not_execute(self):
        with patch("agent_runner.subprocess.run") as run:
            result = run_check("automation-tests")

        run.assert_not_called()
        self.assertFalse(result["executed"])
        self.assertIsNone(result["returncode"])

    def test_unknown_check_is_rejected(self):
        with self.assertRaises(ValueError):
            run_check("deploy-production", execute=True)

    def test_execute_approved_check_uses_shell_false(self):
        with patch("agent_runner.subprocess.run") as run:
            run.return_value.returncode = 0
            result = run_check("git-diff-check", execute=True)

        run.assert_called_once()
        _, kwargs = run.call_args
        self.assertFalse(kwargs["shell"])
        self.assertFalse(kwargs["check"])
        self.assertTrue(result["executed"])
        self.assertEqual(result["returncode"], 0)

    def test_allow_list_is_explicit_and_small(self):
        self.assertEqual(
            set(SAFE_CHECKS),
            {"automation-tests", "git-diff-check"},
        )


if __name__ == "__main__":
    unittest.main()
