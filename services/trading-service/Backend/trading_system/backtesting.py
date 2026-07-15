from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from math import sqrt
from typing import Any

import pandas as pd

from Backend.domain.engine.strategy_engine import StrategyEngine
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.logging import get_logger
from Backend.trading_system.risk import GlobalRiskConfig, GlobalRiskManager
from Backend.trading_system.slippage import SlippageModel

@dataclass(slots=True)
class BacktestTrade:
    symbol: str
    strategy_name: str
    side: str
    quantity: int
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    target_price: float
    pnl: float
    rr: float
    exit_reason: str
    gross_pnl: float = 0.0
    total_costs: float = 0.0
    slippage_cost: float = 0.0
    brokerage: float = 0.0
    taxes: float = 0.0
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entry_time"] = self.entry_time.isoformat()
        payload["exit_time"] = self.exit_time.isoformat()
        return payload


@dataclass(slots=True)
class BacktestMetrics:
    total_trades: int
    win_rate: float
    pnl: float
    max_drawdown: float
    sharpe_ratio: float
    gross_pnl: float = 0.0
    total_costs: float = 0.0
    net_pnl: float = 0.0
    expectancy: float = 0.0
    rejected_signal_count: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    average_latency_ms: float = 0.0
    rr_distribution: list[float] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "pnl": self.pnl,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "gross_pnl": self.gross_pnl,
            "total_costs": self.total_costs,
            "net_pnl": self.net_pnl,
            "expectancy": self.expectancy,
            "rejected_signal_count": self.rejected_signal_count,
            "rejection_reasons": dict(self.rejection_reasons),
            "average_latency_ms": self.average_latency_ms,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.summary()
        payload["rr_distribution"] = self.rr_distribution
        payload["trades"] = self.trades
        return payload


class BacktestEngine:
    def __init__(
        self,
        strategy_engine: StrategyEngine | None = None,
        slippage_model: SlippageModel | None = None,
        risk_manager: GlobalRiskManager | None = None,
        brokerage_per_order: float | None = None,
        brokerage_bps: float | None = None,
        taxes_bps: float | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self.strategy_engine = strategy_engine or StrategyEngine()
        self.slippage_model = slippage_model or SlippageModel()
        self.risk_manager = risk_manager or GlobalRiskManager()
        self.brokerage_per_order = _float_env("BACKTEST_BROKERAGE_PER_ORDER", brokerage_per_order, 20.0)
        self.brokerage_bps = _float_env("BACKTEST_BROKERAGE_BPS", brokerage_bps, 0.0)
        self.taxes_bps = _float_env("BACKTEST_TAXES_BPS", taxes_bps, 2.5)
        self.latency_ms = int(_float_env("BACKTEST_LATENCY_MS", latency_ms, 0.0))
        self.logger = get_logger(__name__)

    def run(
        self,
        *,
        candles: list[dict[str, Any]] | pd.DataFrame,
        signals: list[StrategySignal] | None = None,
        strategy_name: str = "amd",
        symbol: str,
        capital: float = 100_000.0,
        risk_pct: float = 1.0,
        rr_ratio: float = 2.0,
        min_score: float = 10.0,
    ) -> BacktestMetrics:
        frame = self._normalize_candles(candles)
        if frame.empty:
            return BacktestMetrics(0, 0.0, 0.0, 0.0, 0.0)

        self.risk_manager.config = GlobalRiskConfig(
            starting_equity=capital,
            max_daily_loss_pct=self.risk_manager.config.max_daily_loss_pct,
            max_trades_per_day=self.risk_manager.config.max_trades_per_day,
            max_drawdown_pct=self.risk_manager.config.max_drawdown_pct,
            min_signal_score=min_score,
            max_stale_seconds=10**9,
        )
        self.risk_manager.equity = float(capital)
        self.risk_manager.peak_equity = float(capital)
        self.risk_manager.daily_pnl.clear()
        self.risk_manager.daily_trades.clear()
        self.risk_manager.kill_switch_active = False

        context = StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio)
        trades: list[BacktestTrade] = []
        equity_curve = [float(capital)]
        open_signal: StrategySignal | None = None
        entry_index: int | None = None
        entry_price = 0.0
        quantity = 0
        seen_signal_keys: set[tuple[str, datetime, str]] = set()
        rejected_signal_count = 0
        rejection_reasons: dict[str, int] = {}

        for index in range(1, len(frame)):
            row = frame.iloc[index]
            if open_signal is not None and entry_index is not None:
                maybe_trade = self._try_exit(frame, index, open_signal, entry_index, entry_price, quantity)
                if maybe_trade is not None:
                    trades.append(maybe_trade)
                    equity_curve.append(equity_curve[-1] + maybe_trade.pnl)
                    self.risk_manager.record_realized_pnl(maybe_trade.pnl, maybe_trade.exit_time)
                    open_signal = None
                    entry_index = None
                    quantity = 0
                    entry_price = 0.0
                    if self.risk_manager.kill_switch_active:
                        break

            if open_signal is not None:
                continue

            candidate_signals = self._signals_for_bar(
                frame=frame,
                index=index,
                context=context,
                strategy_name=strategy_name,
                provided_signals=signals,
            )
            for signal in candidate_signals:
                key = (signal.symbol, signal.signal_time, signal.side)
                if key in seen_signal_keys:
                    rejected_signal_count += 1
                    _increment_reason(rejection_reasons, "duplicate_signal")
                    continue
                seen_signal_keys.add(key)
                if self._score(signal) < min_score:
                    rejected_signal_count += 1
                    _increment_reason(rejection_reasons, "below_min_score")
                    continue
                valid, reason = self.risk_manager.validate_signal(signal, now=pd.Timestamp(row["timestamp"]).to_pydatetime())
                if not valid:
                    rejected_signal_count += 1
                    _increment_reason(rejection_reasons, _reason_key(reason))
                    self.logger.info("backtest_signal_rejected", {"symbol": symbol, "reason": reason, "event": "backtest_signal_rejected"})
                    continue
                open_signal = signal
                entry_index = index
                raw_entry = float(row["open"])
                entry_price = self.slippage_model.apply(raw_entry, signal.side, "entry", frame, index)
                signal.metadata["backtest_raw_entry_price"] = raw_entry
                quantity = max(1, int(signal.metadata.get("quantity", 1)))
                self.risk_manager.record_trade_opened(signal.signal_time)
                self.logger.info("backtest_trade_opened", {"symbol": symbol, "side": signal.side, "entry": entry_price, "event": "backtest_trade_opened"})
                break

        if open_signal is not None and entry_index is not None:
            final_index = len(frame) - 1
            final_row = frame.iloc[final_index]
            exit_price = self.slippage_model.apply(float(final_row["close"]), open_signal.side, "exit", frame, final_index)
            trade = self._build_trade(
                open_signal,
                entry_price,
                exit_price,
                entry_index,
                final_index,
                quantity,
                "end_of_data",
                frame,
                raw_exit_price=float(final_row["close"]),
            )
            trades.append(trade)
            equity_curve.append(equity_curve[-1] + trade.pnl)

        return self._metrics(
            trades,
            equity_curve,
            rejected_signal_count=rejected_signal_count,
            rejection_reasons=rejection_reasons,
        )

    def _try_exit(
        self,
        frame: pd.DataFrame,
        index: int,
        signal: StrategySignal,
        entry_index: int,
        entry_price: float,
        quantity: int,
    ) -> BacktestTrade | None:
        row = frame.iloc[index]
        side = signal.side.upper()
        low = float(row["low"])
        high = float(row["high"])
        stop = float(signal.stop_loss)
        target = float(signal.target_price)

        if side == "BUY":
            stop_hit = low <= stop
            target_hit = high >= target
        else:
            stop_hit = high >= stop
            target_hit = low <= target

        if not stop_hit and not target_hit:
            return None

        if stop_hit and target_hit:
            exit_reason = "stop_loss"
            raw_exit = stop
        elif stop_hit:
            exit_reason = "stop_loss"
            raw_exit = stop
        else:
            exit_reason = "target"
            raw_exit = target

        exit_price = self.slippage_model.apply(raw_exit, side, "exit", frame, index)
        return self._build_trade(
            signal,
            entry_price,
            exit_price,
            entry_index,
            index,
            quantity,
            exit_reason,
            frame,
            raw_exit_price=raw_exit,
        )

    def _build_trade(
        self,
        signal: StrategySignal,
        entry_price: float,
        exit_price: float,
        entry_index: int,
        exit_index: int,
        quantity: int,
        exit_reason: str,
        frame: pd.DataFrame,
        raw_exit_price: float | None = None,
    ) -> BacktestTrade:
        direction = 1 if signal.side.upper() == "BUY" else -1
        gross_pnl = (float(exit_price) - float(entry_price)) * direction * int(quantity)
        raw_entry = float(signal.metadata.get("backtest_raw_entry_price") or entry_price)
        raw_exit = float(raw_exit_price if raw_exit_price is not None else exit_price)
        slippage_cost = (
            abs(float(entry_price) - raw_entry) + abs(float(exit_price) - raw_exit)
        ) * int(quantity)
        turnover = (abs(float(entry_price)) + abs(float(exit_price))) * int(quantity)
        brokerage = self.brokerage_per_order * 2 + turnover * self.brokerage_bps / 10_000.0
        taxes = turnover * self.taxes_bps / 10_000.0
        total_costs = brokerage + taxes
        pnl = gross_pnl - total_costs
        risk = max(abs(float(entry_price) - float(signal.stop_loss)), 1e-9)
        reward = (float(exit_price) - float(entry_price)) * direction
        return BacktestTrade(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            side=signal.side,
            quantity=int(quantity),
            entry_time=pd.Timestamp(frame.iloc[entry_index]["timestamp"]).to_pydatetime(),
            exit_time=pd.Timestamp(frame.iloc[exit_index]["timestamp"]).to_pydatetime(),
            entry_price=float(entry_price),
            exit_price=float(exit_price),
            stop_loss=float(signal.stop_loss),
            target_price=float(signal.target_price),
            pnl=round(float(pnl), 2),
            rr=float(reward / risk),
            exit_reason=exit_reason,
            gross_pnl=round(float(gross_pnl), 2),
            total_costs=round(float(total_costs), 2),
            slippage_cost=round(float(slippage_cost), 2),
            brokerage=round(float(brokerage), 2),
            taxes=round(float(taxes), 2),
            latency_ms=self.latency_ms,
            metadata={"signal_score": self._score(signal)},
        )

    def _metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[float],
        *,
        rejected_signal_count: int = 0,
        rejection_reasons: dict[str, int] | None = None,
    ) -> BacktestMetrics:
        total = len(trades)
        wins = sum(1 for trade in trades if trade.pnl > 0)
        pnl = sum(trade.pnl for trade in trades)
        returns = [trade.pnl / max(abs(trade.entry_price * trade.quantity), 1.0) for trade in trades]
        sharpe = self._sharpe(returns)
        total_costs = sum(trade.total_costs for trade in trades)
        gross_pnl = sum(trade.gross_pnl for trade in trades)
        avg_latency = sum(trade.latency_ms for trade in trades) / total if total else 0.0
        return BacktestMetrics(
            total_trades=total,
            win_rate=wins / total if total else 0.0,
            pnl=round(float(pnl), 2),
            max_drawdown=self._max_drawdown(equity_curve),
            sharpe_ratio=sharpe,
            gross_pnl=round(float(gross_pnl), 2),
            total_costs=round(float(total_costs), 2),
            net_pnl=round(float(pnl), 2),
            expectancy=round(float(pnl) / total, 2) if total else 0.0,
            rejected_signal_count=rejected_signal_count,
            rejection_reasons=dict(rejection_reasons or {}),
            average_latency_ms=round(float(avg_latency), 2),
            rr_distribution=[trade.rr for trade in trades],
            trades=[trade.to_dict() for trade in trades],
        )

    def _signals_for_bar(
        self,
        *,
        frame: pd.DataFrame,
        index: int,
        context: StrategyContext,
        strategy_name: str,
        provided_signals: list[StrategySignal] | None,
    ) -> list[StrategySignal]:
        if provided_signals is None:
            return self.strategy_engine.run(strategy_name, frame.iloc[:index], context)

        bar_time = pd.Timestamp(frame.iloc[index - 1]["timestamp"]).to_pydatetime().replace(tzinfo=None)
        previous_time = (
            pd.Timestamp(frame.iloc[index - 2]["timestamp"]).to_pydatetime().replace(tzinfo=None)
            if index >= 2
            else datetime.min
        )
        return [
            signal
            for signal in provided_signals
            if previous_time < signal.signal_time.replace(tzinfo=None) <= bar_time
        ]

    @staticmethod
    def _normalize_candles(candles: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
        frame = candles.copy() if isinstance(candles, pd.DataFrame) else pd.DataFrame(candles)
        if frame.empty:
            return frame
        if "timestamp" not in frame.columns:
            frame["timestamp"] = pd.RangeIndex(start=0, stop=len(frame), step=1)
        for column in ("open", "high", "low", "close"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["volume"] = pd.to_numeric(frame.get("volume", 0), errors="coerce").fillna(0.0)
        frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        return frame

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        peak = equity_curve[0] if equity_curve else 0.0
        max_dd = 0.0
        for equity in equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
        return float(max_dd)

    @staticmethod
    def _sharpe(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        series = pd.Series(returns)
        std = float(series.std(ddof=1))
        if std <= 0:
            return 0.0
        return float(series.mean() / std * sqrt(len(returns)))

    @staticmethod
    def _score(signal: StrategySignal) -> float:
        for key in ("total_score", "score"):
            if key in signal.metadata:
                return float(signal.metadata[key])
        return 0.0


def _float_env(name: str, value: float | int | None, default: float) -> float:
    if value is not None:
        return float(value)
    raw = os.getenv(name)
    if raw in {None, ""}:
        return float(default)
    return float(raw)


def _increment_reason(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1


def _reason_key(reason: Any) -> str:
    normalized = str(reason or "risk_rejected").strip().lower().replace(" ", "_")
    return normalized[:80] or "risk_rejected"
