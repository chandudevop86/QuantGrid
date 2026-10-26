"""Regression tests for cancellation races in the backtest coordinator."""

import threading

import pytest

from Backend.application import backtest_jobs


@pytest.mark.parametrize("raise_error", [False, True])
def test_cancel_during_calculation_preserves_cancelled_state(monkeypatch, raise_error):
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    monkeypatch.setattr(backtest_jobs, "_ensure_recovered_jobs", lambda: None)
    monkeypatch.setattr(backtest_jobs, "get_backtest_job_record", lambda job_id: None)
    monkeypatch.setattr(backtest_jobs, "_persist_job", lambda job: None)
    monkeypatch.setattr(backtest_jobs, "_strategy_payload", lambda payload, strategy: {"strategy_name": strategy})

    def calculation(payload):
        entered.set()
        assert release.wait(timeout=5), "test calculation was not released"
        if raise_error:
            raise RuntimeError("calculation failed after cancellation")
        return {"symbol": "NIFTY", "metrics": {"trades": 1}}

    monkeypatch.setattr(backtest_jobs, "_run_calculation", calculation)
    job = backtest_jobs.BacktestJob(
        job_id="cancel-race-test", payload={}, strategies=["amd"], total_strategies=1
    )
    with backtest_jobs._LOCK:
        backtest_jobs._JOBS[job.job_id] = job

    def run():
        try:
            backtest_jobs._run_backtest_job(job.job_id)
        finally:
            completed.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        assert entered.wait(timeout=5), "calculation never started"
        snapshot = backtest_jobs.cancel_backtest_job(job.job_id)
        assert snapshot["status"] == "CANCELLED"
    finally:
        release.set()
        worker.join(timeout=5)
        with backtest_jobs._LOCK:
            backtest_jobs._JOBS.pop(job.job_id, None)

    assert completed.is_set(), "worker did not exit"
    assert job.status == "CANCELLED"
    assert job.partial_results == []
    assert job.completed_strategies == 0
    assert job.result is None
