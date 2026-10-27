"""Regression tests for optional CPU isolation without changing default job semantics."""
from Backend.application import backtest_jobs


def test_default_calculation_remains_in_process(monkeypatch):
    monkeypatch.delenv("QUANTGRID_BACKTEST_PROCESS_ISOLATION", raising=False)
    monkeypatch.setattr(backtest_jobs, "backtesting_module", lambda payload: {"strategy": payload["strategy_name"]})
    assert backtest_jobs._run_calculation({"strategy_name": "amd"}) == {"strategy": "amd"}


def test_opt_in_uses_spawn_process_pool(monkeypatch):
    monkeypatch.setenv("QUANTGRID_BACKTEST_PROCESS_ISOLATION", "1")
    monkeypatch.setattr(backtest_jobs, "_CALCULATION_POOL", None)
    captured = {}

    class Future:
        def result(self, timeout=None):
            return {"ok": True}

    class Pool:
        def __init__(self, *, max_workers, mp_context):
            captured["workers"] = max_workers
            captured["start_method"] = mp_context.get_start_method()

        def shutdown(self, **kwargs):
            pass

        def submit(self, target, payload):
            captured["target"] = target
            captured["payload"] = payload
            return Future()

    monkeypatch.setattr(backtest_jobs, "ProcessPoolExecutor", Pool)
    assert backtest_jobs._run_calculation({"strategy_name": "amd"}) == {"ok": True}
    assert captured["workers"] == 1
    assert captured["start_method"] == "spawn"
    assert captured["target"] is backtest_jobs._calculate_in_process
    assert captured["payload"] == {"strategy_name": "amd"}
    monkeypatch.setattr(backtest_jobs, "_CALCULATION_POOL", None)


def test_process_worker_count_is_bounded(monkeypatch):
    for value, expected in [("1", 1), ("2", 2), ("99", 2), ("0", 1), ("invalid", 1), ("-5", 1)]:
        monkeypatch.setenv("QUANTGRID_BACKTEST_PROCESS_WORKERS", value)
        assert backtest_jobs._process_worker_count() == expected


def test_broken_process_pool_is_reset(monkeypatch):
    import pytest
    from concurrent.futures.process import BrokenProcessPool

    monkeypatch.setenv("QUANTGRID_BACKTEST_PROCESS_ISOLATION", "1")
    monkeypatch.setattr(backtest_jobs, "_CALCULATION_POOL", None)
    pools = []

    class Pool:
        def __init__(self, **kwargs):
            self.shutdown_called = False
            pools.append(self)

        def submit(self, target, payload):
            raise BrokenProcessPool("worker crashed")

        def shutdown(self, **kwargs):
            self.shutdown_called = True

    monkeypatch.setattr(backtest_jobs, "ProcessPoolExecutor", Pool)
    with pytest.raises(BrokenProcessPool):
        backtest_jobs._run_calculation({"strategy_name": "amd"})
    assert pools[0].shutdown_called


def test_isolated_timeout_terminates_own_pool(monkeypatch):
    import pytest
    from concurrent.futures import TimeoutError as FutureTimeout

    monkeypatch.setenv("QUANTGRID_BACKTEST_PROCESS_ISOLATION", "1")
    monkeypatch.setenv("QUANTGRID_BACKTEST_HARD_TIMEOUT_SECONDS", "1")
    pools = []

    class Future:
        def result(self, timeout=None):
            assert 0 < timeout <= 0.25
            raise FutureTimeout()

    class Pool:
        def __init__(self, **kwargs):
            self.terminated = False
            self.shutdown_args = None
            pools.append(self)

        def submit(self, target, payload):
            return Future()

        def terminate_workers(self):
            self.terminated = True

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    monkeypatch.setattr(backtest_jobs, "ProcessPoolExecutor", Pool)
    times = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(backtest_jobs.time, "monotonic", lambda: next(times))
    with pytest.raises(backtest_jobs.BacktestHardTimeout):
        backtest_jobs._run_calculation({"strategy_name": "amd"})
    assert pools[0].terminated
    assert pools[0].shutdown_args["wait"] is False


def test_hard_timeout_config_bounds(monkeypatch):
    for value, expected in [("1", 1), ("60", 60), ("0", 120), ("nan", 120), ("bad", 120), ("9999", 120)]:
        monkeypatch.setenv("QUANTGRID_BACKTEST_HARD_TIMEOUT_SECONDS", value)
        assert backtest_jobs._hard_timeout_seconds() == expected


def test_cancelled_isolated_job_terminates_worker(monkeypatch):
    import pytest
    monkeypatch.setenv("QUANTGRID_BACKTEST_PROCESS_ISOLATION", "1")
    monkeypatch.setattr(backtest_jobs, "_job_cancelled", lambda job_id: True)
    pools = []

    class Pool:
        def __init__(self, **kwargs):
            self.terminated = False
            pools.append(self)
        def submit(self, target, payload):
            return object()
        def terminate_workers(self):
            self.terminated = True
        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(backtest_jobs, "ProcessPoolExecutor", Pool)
    with pytest.raises(backtest_jobs.BacktestCalculationCancelled):
        backtest_jobs._run_calculation({"strategy_name": "amd"}, job_id="cancelled-job")
    assert pools[0].terminated


def _real_worker_sleep_and_record_pid(pid_file: str) -> None:
    """Top-level callable so Python's spawn context can pickle it."""
    import os
    import time
    from pathlib import Path
    Path(pid_file).write_text(str(os.getpid()))
    time.sleep(30)


def test_real_spawned_worker_is_reaped_after_hard_timeout(monkeypatch, tmp_path):
    """Integration: an actual sleeping process must not survive the deadline."""
    import os
    import time
    from pathlib import Path
    import pytest

    pid_file = tmp_path / "worker.pid"
    monkeypatch.setenv("QUANTGRID_BACKTEST_PROCESS_ISOLATION", "1")
    monkeypatch.setenv("QUANTGRID_BACKTEST_HARD_TIMEOUT_SECONDS", "2")
    # Only substitute the workload; keep the real ProcessPoolExecutor.
    monkeypatch.setattr(
        backtest_jobs,
        "_calculate_in_process",
        _real_worker_sleep_and_record_pid,
    )
    with pytest.raises(backtest_jobs.BacktestHardTimeout):
        backtest_jobs._run_calculation(str(pid_file))
    assert pid_file.exists(), "Spawned worker never started; timeout test was inconclusive"
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"Timed-out worker PID {pid} remained alive")
