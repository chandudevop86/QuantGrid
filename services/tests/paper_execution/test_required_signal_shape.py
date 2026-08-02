from __future__ import annotations

from datetime import datetime, timezone

from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.execution import _trade_shape_reason


def test_invalid_signal_shape_rejected():
    signal = StrategySignal(
        strategy_name="test",
        symbol="NIFTY",
        side="BUY",
        entry_price=100,
        stop_loss=105,
        target_price=110,
        signal_time=datetime.now(timezone.utc),
        metadata={"quantity": 75},
    )

    assert _trade_shape_reason(signal) == "BUY signal requires stop < entry < target."
