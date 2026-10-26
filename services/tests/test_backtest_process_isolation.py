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
        def result(self):
            return {"ok": True}

    class Pool:
        def __init__(self, *, max_workers, mp_context):
            captured["workers"] = max_workers
            captured["start_method"] = mp_context.get_start_method()

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
    assert backtest_jobs._CALCULATION_POOL is None
    assert pools[0].shutdown_called
