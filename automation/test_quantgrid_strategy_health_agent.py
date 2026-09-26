import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_health import HealthResult, request_json, summarize
from quantgrid_strategy_health_agent import run_checks


class _Response:
    def __init__(self, status=200):
        self.status = status

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class HealthHelperTests(unittest.TestCase):
    def test_successful_request(self):
        result = request_json("health", "http://example.test", opener=lambda *a, **k: _Response(200))
        self.assertTrue(result.ok)
        self.assertEqual(result.status, 200)

    def test_summary_reports_failure(self):
        result = summarize([
            HealthResult("a", True, 200, "ok"),
            HealthResult("b", False, 500, "http_500"),
        ])
        self.assertFalse(result["healthy"])


class QuantGridStrategyAgentTests(unittest.TestCase):
    @patch("quantgrid_strategy_health_agent.request_json")
    def test_agent_is_diagnostic_only(self, request):
        request.side_effect = [
            HealthResult("backend_health", True, 200, "ok"),
            HealthResult("nifty_1m_candles", True, 200, "ok"),
            HealthResult("signal_route", True, 422, "reachable"),
        ]

        result = run_checks(base_url="http://127.0.0.1:8000")

        self.assertTrue(result["healthy"])
        self.assertEqual(result["mode"], "diagnostic-only")
        self.assertFalse(result["safety"]["live_trading"])
        self.assertFalse(result["safety"]["places_orders"])
        self.assertFalse(result["safety"]["restarts_services"])
        self.assertFalse(result["safety"]["writes_database"])

    @patch("quantgrid_strategy_health_agent.request_json")
    def test_agent_checks_only_expected_routes(self, request):
        request.return_value = HealthResult("ok", True, 200, "ok")

        run_checks(base_url="https://quantgrid.info/api")

        urls = [call.args[1] for call in request.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://quantgrid.info/api/health",
                "https://quantgrid.info/api/market/candles/NIFTY?interval=1m",
                "https://quantgrid.info/api/trading/signals",
            ],
        )


if __name__ == "__main__":
    unittest.main()
