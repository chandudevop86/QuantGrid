from pathlib import Path


def test_completed_backtest_status_overrides_current_strategy_placeholder():
    root = Path(__file__).resolve().parents[1]
    source = (root / "apps" / "frontend" / "src" / "pages" / "Backtesting.tsx").read_text(encoding="utf-8")

    completed_check = 'if (job.status === "COMPLETED") return "All strategies completed";'
    current_strategy_check = "if (job.current_strategy) return titleCase(job.current_strategy);"

    assert completed_check in source
    assert current_strategy_check in source
    assert source.index(completed_check) < source.index(current_strategy_check)


def test_partial_backtest_rank_score_prioritizes_traded_runs():
    root = Path(__file__).resolve().parents[1]
    source = (root / "apps" / "frontend" / "src" / "pages" / "Backtesting.tsx").read_text(encoding="utf-8")

    assert "function backtestRankScore" in source
    assert "number(run.metrics?.total_trades) > 0 ? 1 : 0" in source
    assert "hasTrades * 1_000_000_000" in source
