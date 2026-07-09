from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))


@pytest.fixture(autouse=True)
def _isolated_backtest_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_JOB_STORE_DB_FILE", str(tmp_path / "backtest_jobs.sqlite3"))
    from Backend.application import backtest_job_store

    backtest_job_store.DB_FILE = tmp_path / "backtest_jobs.sqlite3"
    yield


def _fake_result(strategy: str) -> dict:
    return {
        "symbol": "NIFTY",
        "metrics": {
            "total_trades": 1,
            "win_rate": 1.0,
            "net_pnl": 100 if strategy == "breakout" else 50,
            "pnl": 100 if strategy == "breakout" else 50,
            "sharpe_ratio": 2 if strategy == "breakout" else 1,
            "max_drawdown": 0.01,
        },
        "cost_model": {},
        "equity_curve": [{"index": 0, "equity": 100000}, {"index": 1, "equity": 100100}],
        "recent_outcomes": [],
    }


def _wait_for(predicate, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("condition not reached")


def test_backtest_job_completes_with_ranked_partial_results(monkeypatch):
    from Backend.application import backtest_jobs

    backtest_jobs.reset_backtest_jobs_for_tests()
    monkeypatch.setattr(backtest_jobs, "backtesting_module", lambda payload: _fake_result(payload["strategy_name"]))

    started = backtest_jobs.start_backtest_job({"symbol": "NIFTY", "strategies": ["amd", "breakout"], "expected_seconds": 5})

    assert started["status"] == "QUEUED"
    assert started["message"] == "Backtest has been queued and will start shortly."

    finished = _wait_for(lambda: backtest_jobs.get_backtest_job(started["job_id"]) if backtest_jobs.get_backtest_job(started["job_id"])["status"] == "COMPLETED" else None)

    assert finished["completed_strategies"] == 2
    assert finished["progress_pct"] == 100
    assert finished["result"]["best_strategy"] == "breakout"
    assert len(finished["partial_results"]) == 2
    assert finished["message"] == "Backtest completed successfully."


def test_backtest_job_can_be_read_after_memory_cache_is_cleared(monkeypatch):
    from Backend.application import backtest_jobs

    backtest_jobs.reset_backtest_jobs_for_tests()
    monkeypatch.setattr(backtest_jobs, "backtesting_module", lambda payload: _fake_result(payload["strategy_name"]))

    started = backtest_jobs.start_backtest_job({"symbol": "NIFTY", "strategies": ["amd"], "expected_seconds": 5})
    finished = _wait_for(lambda: backtest_jobs.get_backtest_job(started["job_id"]) if backtest_jobs.get_backtest_job(started["job_id"])["status"] == "COMPLETED" else None)

    with backtest_jobs._LOCK:
        backtest_jobs._JOBS.clear()

    reloaded = backtest_jobs.get_backtest_job(finished["job_id"])

    assert reloaded["status"] == "COMPLETED"
    assert reloaded["result"]["best_strategy"] == "amd"
    assert reloaded["partial_results"] == finished["partial_results"]


def test_backtest_job_reports_timeout_without_losing_partial_results(monkeypatch):
    from Backend.application import backtest_jobs

    backtest_jobs.reset_backtest_jobs_for_tests()

    def slow(payload):
        time.sleep(0.05)
        return _fake_result(payload["strategy_name"])

    monkeypatch.setattr(backtest_jobs, "backtesting_module", slow)

    started = backtest_jobs.start_backtest_job({"symbol": "NIFTY", "strategies": ["amd", "breakout", "mtf"], "expected_seconds": 0.01})
    timed_out = _wait_for(lambda: backtest_jobs.get_backtest_job(started["job_id"]) if backtest_jobs.get_backtest_job(started["job_id"])["status"] == "TIMEOUT" else None)

    assert "exceeded the expected execution time" in timed_out["message"]
    assert timed_out["partial_results"]

    completed = _wait_for(lambda: backtest_jobs.get_backtest_job(started["job_id"]) if backtest_jobs.get_backtest_job(started["job_id"])["status"] == "COMPLETED" else None)
    assert completed["completed_strategies"] == 3


def test_backtest_job_cancel_is_reported(monkeypatch):
    from Backend.application import backtest_jobs

    backtest_jobs.reset_backtest_jobs_for_tests()

    def slow(payload):
        time.sleep(0.1)
        return _fake_result(payload["strategy_name"])

    monkeypatch.setattr(backtest_jobs, "backtesting_module", slow)

    started = backtest_jobs.start_backtest_job({"symbol": "NIFTY", "strategies": ["amd", "breakout"], "expected_seconds": 5})
    cancelled = backtest_jobs.cancel_backtest_job(started["job_id"])

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["message"] == "Backtest was cancelled."


def test_backtest_api_start_returns_job_id(app_client):
    from conftest import admin_headers
    from Backend.application import backtest_jobs

    backtest_jobs.reset_backtest_jobs_for_tests()
    response = app_client.post(
        "/backtest/start",
        json={"symbol": "NIFTY", "strategies": ["amd"], "expected_seconds": 5},
        headers=admin_headers(app_client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"]
    assert payload["status"] in {"QUEUED", "RUNNING", "COMPLETED"}
