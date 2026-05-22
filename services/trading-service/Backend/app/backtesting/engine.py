from __future__ import annotations

from typing import Any

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestResult, BacktestTrade
from Backend.application.trading_service import TradingService
from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.signal import StrategySignal


class BacktestEngine:
    def __init__(self, service: TradingService | None = None) -> None:
        self.service = service or TradingService()

    def run(
        self,
        *,
        strategy: str,
        symbol: str,
        candles: list[dict[str, Any]],
        capital: float = 100_000,
        risk_pct: float = 1.0,
        rr_ratio: float = 2.0,
    ) -> BacktestResult:
        signals = self.service.run_strategy(
            strategy_name=strategy,
            data=candles,
            symbol=symbol,
            capital=capital,
            risk_pct=risk_pct,
            rr_ratio=rr_ratio,
        )
        frame = IndicatorService().prepare(candles)
        trades = [trade for signal in signals if (trade := self._simulate_signal(signal, frame)) is not None]
        return BacktestResult(strategy=strategy, symbol=symbol.upper(), metrics=calculate_metrics(trades), trades=trades)

    @staticmethod
    def _simulate_signal(signal: StrategySignal, frame) -> BacktestTrade | None:
        matches = frame[frame["timestamp"] >= signal.signal_time]
        if matches.empty:
            return None

        entry_index = int(matches.index[0])
        entry = float(signal.entry_price)
        stop = float(signal.stop_loss)
        target = float(signal.target_price)
        quantity = int(signal.metadata.get("quantity") or 1)
        side = signal.side.upper()
        exit_price = float(frame.iloc[-1]["close"])
        exit_time = frame.iloc[-1]["timestamp"].isoformat()
        outcome = "end_of_data"

        for index in range(entry_index + 1, len(frame)):
            row = frame.iloc[index]
            high = float(row["high"])
            low = float(row["low"])
            if side == "BUY":
                if low <= stop:
                    exit_price = stop
                    outcome = "loss"
                    exit_time = row["timestamp"].isoformat()
                    break
                if high >= target:
                    exit_price = target
                    outcome = "win"
                    exit_time = row["timestamp"].isoformat()
                    break
            else:
                if high >= stop:
                    exit_price = stop
                    outcome = "loss"
                    exit_time = row["timestamp"].isoformat()
                    break
                if low <= target:
                    exit_price = target
                    outcome = "win"
                    exit_time = row["timestamp"].isoformat()
                    break

        direction = 1 if side == "BUY" else -1
        pnl = (exit_price - entry) * direction * quantity
        risk = abs(entry - stop)
        reward = abs(target - entry)
        return BacktestTrade(
            strategy=signal.strategy_name,
            symbol=signal.symbol,
            side=side,
            entry=round(entry, 4),
            stop_loss=round(stop, 4),
            target=round(target, 4),
            quantity=quantity,
            entry_time=signal.signal_time.isoformat(),
            exit_time=exit_time,
            exit_price=round(exit_price, 4),
            pnl=round(pnl, 2),
            rr=round(reward / risk, 2) if risk > 0 else 0.0,
            outcome=outcome,
        )
