import pytest

from Backend.application.portfolio.paper_short_accounting import PaperPosition


def test_short_partial_cover_and_final_cover():
    p = PaperPosition()
    p.apply_fill("SELL", 10, 100, 2)
    assert (p.quantity, p.average_price, p.realized_pnl) == (-10, 100, -2)
    assert p.unrealized_pnl(90) == 100
    p.apply_fill("BUY", 4, 90, 1)
    assert (p.quantity, p.average_price, p.realized_pnl) == (-6, 100, 37)
    p.apply_fill("BUY", 6, 110)
    assert (p.quantity, p.average_price, p.realized_pnl) == (0, 0, -23)


def test_reverse_short_to_long_and_back():
    p = PaperPosition()
    p.apply_fill("SELL", 5, 100)
    p.apply_fill("BUY", 8, 90)
    assert (p.quantity, p.average_price, p.realized_pnl) == (3, 90, 50)
    p.apply_fill("SELL", 5, 95)
    assert (p.quantity, p.average_price, p.realized_pnl) == (-2, 95, 65)


@pytest.mark.parametrize("side,qty,price,fees", [
    ("HOLD", 1, 100, 0), ("SELL", 0, 100, 0),
    ("SELL", -1, 100, 0), ("SELL", 1, -1, 0),
    ("SELL", 1, float("nan"), 0), ("SELL", 1, 100, -1),
])
def test_invalid_fill_does_not_mutate(side, qty, price, fees):
    p = PaperPosition()
    with pytest.raises(ValueError):
        p.apply_fill(side, qty, price, fees)
    assert p == PaperPosition()
