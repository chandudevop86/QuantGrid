from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True)
class PaperTradeCosts:
    gross_pnl: float
    brokerage: float
    taxes: float
    slippage_cost: float
    total_costs: float
    net_pnl: float

    def to_dict(self) -> dict[str, float]:
        return {
            "gross_pnl": self.gross_pnl,
            "brokerage": self.brokerage,
            "taxes": self.taxes,
            "slippage_cost": self.slippage_cost,
            "total_costs": self.total_costs,
            "net_pnl": self.net_pnl,
        }


def calculate_paper_trade_costs(
    *,
    side: str,
    entry_price: float,
    exit_price: float,
    quantity: int,
) -> PaperTradeCosts:
    """Estimate paper-trade round-trip costs using the same defaults as backtesting.

    The model is intentionally explicit and configurable. It does not claim to reproduce a
    broker contract note; it provides deterministic paper evidence including brokerage,
    tax/fee allowance, and a slippage/spread allowance.
    """
    qty = max(0, int(quantity))
    entry = float(entry_price)
    exit_value_price = float(exit_price)
    direction = 1.0 if str(side).upper() in {"BUY", "CE", "CALL"} else -1.0

    gross = (exit_value_price - entry) * qty * direction
    entry_value = abs(entry * qty)
    exit_value = abs(exit_value_price * qty)
    turnover = entry_value + exit_value

    brokerage_per_order = max(0.0, _float_env("QUANTGRID_PAPER_BROKERAGE_PER_ORDER", 20.0))
    brokerage_bps = max(0.0, _float_env("QUANTGRID_PAPER_BROKERAGE_BPS", 0.0))
    taxes_bps = max(0.0, _float_env("QUANTGRID_PAPER_TAXES_BPS", 2.5))
    slippage_bps = max(0.0, _float_env("QUANTGRID_PAPER_SLIPPAGE_BPS", 5.0))
    spread_bps = max(0.0, _float_env("QUANTGRID_PAPER_SPREAD_BPS", 8.0))

    brokerage = brokerage_per_order * 2.0 + turnover * brokerage_bps / 10000.0
    taxes = turnover * taxes_bps / 10000.0
    effective_slippage_per_side_bps = slippage_bps + spread_bps / 2.0
    slippage_cost = turnover * effective_slippage_per_side_bps / 10000.0
    total_costs = brokerage + taxes + slippage_cost
    net = gross - total_costs

    return PaperTradeCosts(
        gross_pnl=round(gross, 2),
        brokerage=round(brokerage, 2),
        taxes=round(taxes, 2),
        slippage_cost=round(slippage_cost, 2),
        total_costs=round(total_costs, 2),
        net_pnl=round(net, 2),
    )
