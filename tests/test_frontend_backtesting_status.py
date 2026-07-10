from pathlib import Path


def test_completed_backtest_status_overrides_current_strategy_placeholder():
    root = Path(__file__).resolve().parents[1]
    source = (root / "apps" / "frontend" / "src" / "pages" / "Backtesting.tsx").read_text(encoding="utf-8")

    completed_check = 'if (job.status === "COMPLETED") return "All strategies completed";'
    current_strategy_check = "if (job.current_strategy) return titleCase(job.current_strategy);"

    assert completed_check in source
    assert current_strategy_check in source
    assert source.index(completed_check) < source.index(current_strategy_check)
