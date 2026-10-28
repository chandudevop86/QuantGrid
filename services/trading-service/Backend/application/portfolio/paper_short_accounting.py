"""Paper-only signed-position accounting. No broker execution or live order routing."""
from dataclasses import dataclass
from math import isfinite


@dataclass
class PaperPosition:
    quantity: int = 0  # positive=long, negative=short
    average_price: float = 0.0
    realized_pnl: float = 0.0

    def apply_fill(self, side: str, quantity: int, price: float, fees: float = 0.0) -> None:
        """Apply a confirmed paper fill, including partial closes and reversals."""
        if side not in ("BUY", "SELL"):
            raise ValueError("Invalid side")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")
        if not all(isfinite(x) for x in (price, fees)) or price <= 0 or fees < 0:
            raise ValueError("Invalid price or fees")
        delta = quantity if side == "BUY" else -quantity
        previous = self.quantity
        if previous == 0 or (previous > 0) == (delta > 0):
            total = abs(previous) + quantity
            self.average_price = (abs(previous) * self.average_price + quantity * price) / total
            self.quantity += delta
        else:
            closing = min(abs(previous), quantity)
            direction = 1 if previous > 0 else -1
            self.realized_pnl += (price - self.average_price) * closing * direction
            self.quantity += delta
            if self.quantity == 0:
                self.average_price = 0.0
            elif (self.quantity > 0) != (previous > 0):
                self.average_price = price
        self.realized_pnl -= fees

    def unrealized_pnl(self, mark_price: float) -> float:
        if not isfinite(mark_price) or mark_price <= 0:
            raise ValueError("Invalid mark price")
        return (mark_price - self.average_price) * self.quantity
