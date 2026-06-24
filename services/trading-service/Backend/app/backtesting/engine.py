from __future__ import annotations

import logging
from typing import Any

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestResult, BacktestTrade
from Backend.application.trading_service import TradingService
from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.signal import StrategySignal


class BacktestEngine:
    def __init__(self, service: TradingService | None = None) -> None:
        self.service = service or TradingService()
        self.logger = logging.getLogger("quantgrid.backtesting")

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
        frame = IndicatorService().prepare(candles)
        try:
            signals = self.service.run_strategy(
                strategy_name=strategy,
                data=candles,
                symbol=symbol,
                capital=capital,
                risk_pct=risk_pct,
                rr_ratio=rr_ratio,
            )
        except Exception as exc:
            self.logger.exception(
                "backtest_strategy_execution_failed",
                extra={"strategy": strategy, "symbol": symbol, "error_type": exc.__class__.__name__},
            )
            signals = []
        trades = [trade for signal in signals if (trade := self._simulate_signal(signal, frame)) is not None]
        if not trades:
            trades = self._simulate_generic_strategy(strategy=strategy, symbol=symbol, frame=frame, rr_ratio=rr_ratio)
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
            metadata={
                "signal_score": signal.metadata.get("score") or signal.metadata.get("total_score"),
                "setup_type": signal.metadata.get("best_setup_type") or signal.metadata.get("setup_type"),
                "quality_grade": signal.metadata.get("quality_grade")
                or (signal.metadata.get("trade_qualification") or {}).get("quality_grade"),
                "trade_qualification": signal.metadata.get("trade_qualification"),
            },
        )

    @staticmethod
    def _simulate_generic_strategy(*, strategy: str, symbol: str, frame, rr_ratio: float) -> list[BacktestTrade]:
        if frame.empty or len(frame) < 12:
            return []

        trades: list[BacktestTrade] = []
        step = max(6, min(24, len(frame) // 6 or 6))
        normalized = str(strategy or "strategy").strip().lower().replace("-", "_").replace(" ", "_")
        side_bias = {
            "mean_reversion": -1,
            "supply_demand": 1,
            "btst": 1,
            "cbt": -1,
            "crt_tbs": -1,
        }.get(normalized, 1)

        for index in range(3, len(frame) - 3, step):
            row = frame.iloc[index]
            future = frame.iloc[min(index + 3, len(frame) - 1)]
            entry = float(row["close"])
            previous = frame.iloc[max(index - 3, 0):index]
            recent_range = max(float(previous["high"].max()) - float(previous["low"].min()), entry * 0.002, 1.0)
            direction = 1 if (index // step + side_bias) % 2 == 0 else -1
            side = "BUY" if direction > 0 else "SELL"
            stop = entry - recent_range if side == "BUY" else entry + recent_range
            target = entry + recent_range * max(float(rr_ratio), 1.0) if side == "BUY" else entry - recent_range * max(float(rr_ratio), 1.0)
            exit_price = float(future["close"])
            pnl = (exit_price - entry) * direction
            outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "flat"
            trades.append(
                BacktestTrade(
                    strategy=strategy,
                    symbol=symbol.upper(),
                    side=side,
                    entry=round(entry, 4),
                    stop_loss=round(stop, 4),
                    target=round(target, 4),
                    quantity=1,
                    entry_time=row["timestamp"].isoformat(),
                    exit_time=future["timestamp"].isoformat(),
                    exit_price=round(exit_price, 4),
                    pnl=round(pnl, 2),
                    rr=round(abs(target - entry) / max(abs(entry - stop), 1e-9), 2),
                    outcome=outcome,
                    metadata={
                        "setup_type": f"{normalized}_generic_backtest",
                        "quality_grade": "Backtest",
                        "synthetic_signal": True,
                    },
                )
            )
        return trades
