"""Run with: python -m unittest discover -s automation -p 'test_*.py'."""
import unittest

from agent_plan import plan


class PlannerTests(unittest.TestCase):
    def test_plan_is_non_executing(self):
        result = plan({"project": "quantgrid", "task": "Review CI", "checks": ["Python tests"]})
        self.assertEqual(result["execution"], "planning-only")
        self.assertEqual(len(result["stages"]), 4)
        self.assertIn("live trading", result["requires_human_approval"])

    def test_rejects_extra_fields(self):
        with self.assertRaises(ValueError):
            plan({"project": "quantgrid", "task": "x", "checks": ["lint"], "command": "echo hi"})

    def test_rejects_invalid_checks(self):
        with self.assertRaises(ValueError):
            plan({"project": "foodtruck", "task": "x", "checks": []})


if __name__ == "__main__":
    unittest.main()
