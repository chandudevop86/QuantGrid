from pathlib import Path

from Backend.domain.execution_constraints import lot_size_for_symbol


ROOT = Path(__file__).resolve().parents[2]


def test_trade_ticket_and_backend_share_the_nifty_65_unit_lot():
    terminal = (
        ROOT / "apps/frontend/src/features/terminal/TerminalWorkspace.tsx"
    ).read_text(encoding="utf-8")

    assert 'symbol: "NIFTY"' in terminal
    assert "quantity: 65" in terminal
    assert lot_size_for_symbol("NIFTY") == 65
