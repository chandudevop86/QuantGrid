from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

import numpy as np
import pandas as pd

from Backend.application.trading_service import TradingService
from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.risk import GlobalRiskManager
from Backend.trading_system.slippage import SlippageModel


@dataclass
class Trade:
    id: str
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    raw_entry_price: float
    quantity: int
    stop_loss: float
    target_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    raw_exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    gross_pnl: float = 0.0
    total_costs: float = 0.0
    brokerage: float = 0.0
    taxes: float = 0.0
    slippage_cost: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    latency_ms: float = 0.0
    strategy_name: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss) * max(self.quantity, 1)
        return self.pnl / risk if risk > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rr"] = self.rr
        return data


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    gross_pnl: float = 0.0
    total_costs: float = 0.0
    net_pnl: float = 0.0
    pnl: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    average_latency_ms: float = 0.0
    rejected_signal_count: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    strategy_name: str | None = None
    symbol: str | None = None

    @property
    def total_pnl(self) -> float:
        return self.net_pnl

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BacktestEngine:
    """Canonical historical simulator for API, dashboard and compatibility paths."""

    def __init__(
        self,
        strategy: Any | None = None,
        risk_manager: GlobalRiskManager | None = None,
        initial_capital: float = 100_000.0,
        commission_rate: float = 0.0005,
        slippage_rate: float = 0.0002,
        slippage_model: SlippageModel | None = None,
        brokerage_per_order: float = 0.0,
        brokerage_bps: float = 0.0,
        taxes_bps: float = 0.0,
        latency_ms: float = 0.0,
        **_: Any,
    ) -> None:
        self.strategy = strategy
        self.risk_manager = risk_manager or GlobalRiskManager()
        self.initial_capital = float(initial_capital)
        self.commission_rate = float(commission_rate)
        self.slippage_rate = float(slippage_rate)
        self.slippage_model = slippage_model
        self.brokerage_per_order = float(brokerage_per_order)
        self.brokerage_bps = float(brokerage_bps)
        self.taxes_bps = float(taxes_bps)
        self.latency_ms = float(latency_ms)
        self.trading_service = TradingService() if strategy is None else None

    def run(
        self,
        candles: pd.DataFrame | list[dict[str, Any]],
        strategy_name: str | None = None,
        symbol: str | None = None,
        capital: float | None = None,
        risk_pct: float = 1.0,
        rr_ratio: float = 2.0,
        min_score: float = 7.0,
        signals: list[StrategySignal] | None = None,
        **_: Any,
    ) -> BacktestMetrics:
        frame = self._normalize_candles(candles)
        starting_capital = float(capital if capital is not None else self.initial_capital)
        strategy_name = strategy_name or self._strategy_name()
        symbol = str(symbol or self._symbol_from_frame(frame) or "NIFTY").upper()
        if frame.empty:
            return BacktestMetrics(
                equity_curve=[{"index": 0, "equity": starting_capital}],
                strategy_name=strategy_name,
                symbol=symbol,
            )

        self._reset_risk(starting_capital, risk_pct)
        signal_map = self._prepare_signal_map(signals)
        capital_now = starting_capital
        open_trade: Trade | None = None
        closed: list[Trade] = []
        rejected = 0
        rejection_reasons: dict[str, int] = {}
        curve: list[dict[str, Any]] = [{"index": 0, "equity": round(capital_now, 8)}]

        for i, row in frame.iterrows():
            timestamp = self._as_datetime(row["timestamp"])
            open_p, high, low, close = map(float, (row["open"], row["high"], row["low"], row["close"]))

            if open_trade is not None:
                exit_price, reason = self._try_exit(open_trade, high, low)
                if exit_price is not None:
                    self._close_trade(open_trade, timestamp, exit_price, reason, frame, i)
                    capital_now += open_trade.pnl
                    self.risk_manager.record_realized_pnl(open_trade.pnl, timestamp)
                    closed.append(open_trade)
                    open_trade = None

            if open_trade is None:
                candidates = signal_map.get(pd.Timestamp(timestamp), [])
                if candidates:
                    signal = candidates.pop(0)
                else:
                    signal = self._generate_signal(frame, i, strategy_name, symbol, capital_now, risk_pct, rr_ratio, min_score)

                while signal is not None and open_trade is None:
                    signal.metadata = dict(signal.metadata or {})
                    signal.metadata.setdefault("risk_pct", risk_pct)
                    signal.metadata.setdefault("risk_per_trade_pct", risk_pct)
                    signal.metadata.setdefault("rr_ratio", rr_ratio)
                    score = float(signal.metadata.get("total_score", signal.metadata.get("score", 0.0)))

                    if score < min_score:
                        rejected += 1
                        rejection_reasons["below_min_score"] = rejection_reasons.get("below_min_score", 0) + 1
                    else:
                        decision = self._risk_decision(signal, timestamp, capital_now, risk_pct)
                        if not decision[0]:
                            rejected += 1
                            reason = decision[1]
                            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                        else:
                            raw_entry = open_p if signal.metadata.get("next_open") else close
                            signal.metadata["backtest_raw_entry_price"] = raw_entry
                            entry = self._apply_slippage(raw_entry, signal.side, "entry", frame, i)
                            quantity = int(decision[2])
                            if quantity > 0:
                                open_trade = self._build_trade(signal, timestamp, raw_entry, entry, quantity, strategy_name)
                                self.risk_manager.record_trade_opened(timestamp)

                    if open_trade is not None or not candidates:
                        break
                    signal = candidates.pop(0)

            unrealized = self._unrealized(open_trade, close) if open_trade else 0.0
            curve.append({"index": len(curve), "equity": round(capital_now + unrealized, 8), "time": timestamp.isoformat()})

        if open_trade is not None:
            last_i = len(frame) - 1
            last = frame.iloc[last_i]
            timestamp = self._as_datetime(last["timestamp"])
            self._close_trade(open_trade, timestamp, float(last["close"]), "end_of_data", frame, last_i)
            capital_now += open_trade.pnl
            self.risk_manager.record_realized_pnl(open_trade.pnl, timestamp)
            closed.append(open_trade)
            curve[-1] = {"index": len(curve) - 1, "equity": round(capital_now, 8), "time": timestamp.isoformat()}

        return self._calculate_metrics(closed, curve, rejected, rejection_reasons, strategy_name, symbol)

    def _reset_risk(self, capital: float, risk_pct: float) -> None:
        self.risk_manager.equity = capital
        self.risk_manager.peak_equity = capital
        self.risk_manager.kill_switch_active = False
        self.risk_manager.daily_pnl.clear()
        self.risk_manager.daily_trades.clear()
        self.risk_manager.rejections.clear()
        if hasattr(self.risk_manager, "config"):
            self.risk_manager.config.max_stale_seconds = max(int(getattr(self.risk_manager.config, "max_stale_seconds", 60)), 10**9)
            self.risk_manager.config.max_risk_per_trade_pct = max(float(self.risk_manager.config.max_risk_per_trade_pct), float(risk_pct))

    def _risk_decision(self, signal: StrategySignal, timestamp: datetime, capital: float, risk_pct: float) -> tuple[bool, str, int]:
        if hasattr(self.risk_manager, "validate_order"):
            decision = self.risk_manager.validate_order(signal, now=timestamp, capital=capital)
            return bool(decision.accepted), str(decision.reason), int(decision.quantity)
        if hasattr(self.risk_manager, "position_size"):
            result = self.risk_manager.position_size(
                capital=capital,
                risk_pct=risk_pct,
                entry=float(signal.entry_price),
                stop_loss=float(signal.stop_loss),
                lot_size=int(signal.metadata.get("lot_size", 1) or 1),
                max_quantity=signal.metadata.get("max_quantity", signal.metadata.get("quantity")),
            )
            quantity = int(result[0] if isinstance(result, tuple) else result)
            return quantity > 0, "accepted" if quantity > 0 else "position_size_zero", quantity
        if hasattr(self.risk_manager, "size_position"):
            quantity = int(self.risk_manager.size_position(symbol=signal.symbol, entry_price=signal.entry_price, stop_loss=signal.stop_loss, capital=capital))
            return quantity > 0, "accepted" if quantity > 0 else "position_size_zero", quantity
        raise TypeError("Risk manager must expose validate_order(), position_size(), or size_position().")

    def _generate_signal(self, frame: pd.DataFrame, index: int, strategy_name: str, symbol: str, capital: float, risk_pct: float, rr_ratio: float, min_score: float) -> StrategySignal | None:
        if self.strategy is not None:
            try:
                return self.strategy.generate_signal(frame.iloc[: index + 1])
            except Exception:
                return None
        if self.trading_service is None:
            self.trading_service = TradingService()
        try:
            signals = self.trading_service.run_strategy(
                strategy_name=strategy_name,
                data=frame.iloc[: index + 1].to_dict("records"),
                symbol=symbol,
                capital=capital,
                risk_pct=risk_pct,
                rr_ratio=rr_ratio,
                params={},
            )
            return signals[0] if signals else None
        except Exception:
            return None

    @staticmethod
    def _prepare_signal_map(signals: list[StrategySignal] | None) -> dict[pd.Timestamp, list[StrategySignal]]:
        result: dict[pd.Timestamp, list[StrategySignal]] = {}
        for signal in signals or []:
            result.setdefault(pd.Timestamp(signal.signal_time), []).append(signal)
        return result

    def _build_trade(self, signal: StrategySignal, timestamp: datetime, raw_entry: float, entry_price: float, quantity: int, strategy_name: str) -> Trade:
        return Trade(
            id=f"bt_{timestamp.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
            symbol=str(signal.symbol).upper(),
            side=str(signal.side).upper(),
            entry_time=timestamp,
            entry_price=float(entry_price),
            raw_entry_price=float(raw_entry),
            quantity=quantity,
            stop_loss=float(signal.stop_loss),
            target_price=float(signal.target_price),
            strategy_name=strategy_name,
            metadata=dict(signal.metadata or {}),
            latency_ms=self.latency_ms,
        )

    @staticmethod
    def _try_exit(trade: Trade, high: float, low: float) -> tuple[Optional[float], Optional[str]]:
        if trade.side == "BUY":
            stop_hit, target_hit = low <= trade.stop_loss, high >= trade.target_price
        else:
            stop_hit, target_hit = high >= trade.stop_loss, low <= trade.target_price
        if stop_hit and target_hit:
            return trade.stop_loss, "stop_loss"
        if stop_hit:
            return trade.stop_loss, "stop_loss"
        if target_hit:
            return trade.target_price, "target"
        return None, None

    def _close_trade(self, trade: Trade, timestamp: datetime, raw_exit: float, reason: str, frame: pd.DataFrame, index: int) -> None:
        trade.exit_time = timestamp
        trade.raw_exit_price = float(raw_exit)
        trade.exit_price = self._apply_slippage(raw_exit, trade.side, "exit", frame, index)
        trade.exit_reason = reason
        entry_value = trade.entry_price * trade.quantity
        exit_value = trade.exit_price * trade.quantity
        trade.brokerage = self.brokerage_per_order * 2.0 + (entry_value + exit_value) * self.brokerage_bps / 10000.0
        trade.taxes = (entry_value + exit_value) * self.taxes_bps / 10000.0
        trade.total_costs = trade.brokerage + trade.taxes
        if self.brokerage_per_order == 0.0 and self.brokerage_bps == 0.0 and self.taxes_bps == 0.0:
            trade.total_costs += (entry_value + exit_value) * self.commission_rate
        trade.gross_pnl = ((trade.exit_price - trade.entry_price) if trade.side == "BUY" else (trade.entry_price - trade.exit_price)) * trade.quantity
        trade.pnl = trade.gross_pnl - trade.total_costs
        trade.pnl_percent = trade.pnl / entry_value if entry_value else 0.0
        trade.slippage_cost = (abs(trade.entry_price - trade.raw_entry_price) + abs(trade.exit_price - trade.raw_exit_price)) * trade.quantity

    def _apply_slippage(self, price: float, side: str, event: str, frame: pd.DataFrame, index: int) -> float:
        if self.slippage_model is not None:
            return float(self.slippage_model.apply(price, side, event, frame, index))
        slip = float(price) * self.slippage_rate
        return float(price + slip if (event == "entry" and side.upper() == "BUY") or (event == "exit" and side.upper() == "SELL") else price - slip)

    @staticmethod
    def _unrealized(trade: Trade, close: float) -> float:
        return ((close - trade.entry_price) if trade.side == "BUY" else (trade.entry_price - close)) * trade.quantity

    def _calculate_metrics(self, trades: list[Trade], curve: list[dict[str, Any]], rejected: int, reasons: dict[str, int], strategy_name: str, symbol: str) -> BacktestMetrics:
        total = len(trades)
        wins, losses = [t for t in trades if t.pnl > 0], [t for t in trades if t.pnl < 0]
        gross_profit, gross_loss = sum(t.pnl for t in wins), abs(sum(t.pnl for t in losses))
        equities = np.asarray([float(x["equity"]) for x in curve], dtype=float)
        returns = np.diff(equities) / np.where(equities[:-1] == 0, 1.0, equities[:-1]) if len(equities) > 1 else np.array([])
        sharpe = float(np.sqrt(252) * np.mean(returns) / np.std(returns)) if len(returns) > 1 and np.std(returns) > 0 else 0.0
        if len(equities):
            peaks = np.maximum.accumulate(equities)
            max_dd = float(np.min((equities - peaks) / np.where(peaks == 0, 1.0, peaks)))
        else:
            max_dd = 0.0
        net = sum(t.pnl for t in trades)
        return BacktestMetrics(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / total if total else 0.0,
            gross_pnl=sum(t.gross_pnl for t in trades),
            total_costs=sum(t.total_costs for t in trades),
            net_pnl=net,
            pnl=net,
            expectancy=net / total if total else 0.0,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            profit_factor=gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
            average_latency_ms=sum(t.latency_ms for t in trades) / total if total else 0.0,
            rejected_signal_count=rejected,
            rejection_reasons=reasons,
            equity_curve=curve,
            trades=[t.to_dict() for t in trades],
            strategy_name=strategy_name,
            symbol=symbol,
        )

    @staticmethod
    def _normalize_candles(candles: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
        df = candles.copy() if isinstance(candles, pd.DataFrame) else pd.DataFrame(candles)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df.columns = [str(c).strip().lower() for c in df.columns]
        aliases = {"datetime": "timestamp", "date": "timestamp", "time": "timestamp"}
        df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns and v not in df.columns})
        missing = {"timestamp", "open", "high", "low", "close"} - set(df.columns)
        if missing:
            raise ValueError(f"Missing required candle columns: {sorted(missing)}")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    def _strategy_name(self) -> str:
        return str(getattr(self.strategy, "name", None) or getattr(self.strategy, "strategy_name", None) or "unknown")

    @staticmethod
    def _symbol_from_frame(frame: pd.DataFrame) -> str | None:
        return str(frame["symbol"].dropna().iloc[0]) if "symbol" in frame.columns and not frame["symbol"].dropna().empty else None

    @staticmethod
    def _as_datetime(value: Any) -> datetime:
        ts = pd.Timestamp(value)
        return ts.to_pydatetime().replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.to_pydatetime()
