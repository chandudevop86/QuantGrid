from pathlib import Path

from Backend.domain.execution_constraints import lot_size_for_symbol


ROOT = Path(__file__).resolve().parents[1]


def test_trade_ticket_and_backend_share_the_nifty_65_unit_lot():
    trade = (ROOT / "apps/frontend/src/pages/Trade.tsx").read_text(encoding="utf-8")
    assert 'symbol === "NIFTY" ? 65 : 1' in trade
    assert 'useState("65")' in trade
    assert "step={lotSize}" in trade
    assert lot_size_for_symbol("NIFTY") == 65
