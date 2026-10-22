"""Regression guard: HTTP signal reads must never create trade journal rows."""

import ast
from pathlib import Path


def test_latest_signals_does_not_write_trade_journal():
    root = Path(__file__).resolve().parents[1]
    path = root / "trading-service" / "Backend" / "presentation" / "api" / "professional_api.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "latest_signals"
    )
    writers = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"create_trade_journal_entry", "patch_trade_journal_entry"}
    ]
    assert not writers, "GET /api/signals must not create or modify trade journal entries"
