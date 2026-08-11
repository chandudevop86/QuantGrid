from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any, Tuple


@dataclass
class Trade:
    id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_time: datetime
    entry_price: float
    raw_entry_price: float
    quantity: float
    stop_loss: float
    target: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    raw_exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    pnl_percent: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    equity_curve: List[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(
        self,
        strategy,
        risk_manager,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.0005,  # 0.05%
        slippage_rate: float = 0.0002,    # 0.02%
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

    def run(self, candles: pd.DataFrame) -> BacktestMetrics:
        """Executes backtest over provided candle data."""
        frame = self._normalize_candles(candles)
        
        # Configure Risk Manager before empty frame checks
        if hasattr(self.risk_manager, "config"):
            self.risk_manager.config.max_stale_seconds = 10**9

        if frame.empty:
            return BacktestMetrics(equity_curve=[self.initial_capital])

        capital = self.initial_capital
        open_trade: Optional[Trade] = None
        closed_trades: List[Trade] = []
        equity_curve: List[float] = [capital]

        for i in range(len(frame)):
            row = frame.iloc[i]
            timestamp = row["timestamp"]
            open_p, high, low, close = row["open"], row["high"], row["low"], row["close"]

            # 1. Check exit condition on open trade
            if open_trade is not None:
                exit_price, reason = self._try_exit(open_trade, open_p, high, low, close, row)
                if exit_price is not None:
                    open_trade = self._close_trade(open_trade, timestamp, exit_price, reason)
                    capital += open_trade.pnl
                    closed_trades.append(open_trade)
                    open_trade = None

            # 2. Check for new signals if no open trade exists
            if open_trade is None:
                current_data = frame.iloc[: i + 1]
                signal = self.strategy.generate_signal(current_data)

                if signal is not None:
                    # Apply slippage on entry
                    raw_entry = open_p if "next_open" in signal.metadata else close
                    entry_price = self._apply_slippage(raw_entry, signal.side, is_entry=True)
                    
                    # Store for trade metrics calculation
                    signal.metadata["backtest_raw_entry_price"] = raw_entry

                    # Position Sizing & Risk Checks
                    quantity = self.risk_manager.size_position(
                        symbol=signal.symbol,
                        entry_price=entry_price,
                        stop_loss=signal.stop_loss,
                        capital=capital,
                    )

                    if quantity > 0:
                        open_trade = self._build_trade(signal, timestamp, entry_price, quantity)

            # 3. Track Mark-to-Market Equity Curve per candle
            current_unrealized_pnl = 0.0
            if open_trade is not None:
                if open_trade.side == "BUY":
                    current_unrealized_pnl = (close - open_trade.entry_price) * open_trade.quantity
                else:
                    current_unrealized_pnl = (open_trade.entry_price - close) * open_trade.quantity
            
            equity_curve.append(capital + current_unrealized_pnl)

        # Force close any remaining open position at the end of data series
        if open_trade is not None:
            last_row = frame.iloc[-1]
            open_trade = self._close_trade(
                open_trade, last_row["timestamp"], last_row["close"], "end_of_data"
            )
            capital += open_trade.pnl
            closed_trades.append(open_trade)
            equity_curve[-1] = capital

        return self._calculate_metrics(closed_trades, equity_curve)

    def _try_exit(
        self, trade: Trade, open_p: float, high: float, low: float, close: float, row: pd.Series
    ) -> Tuple[Optional[float], Optional[str]]:
        """Evaluates whether stop loss or target is triggered for an open trade."""
        stop, target = trade.stop_loss, trade.target
        side = trade.side

        if side == "BUY":
            stop_hit = low <= stop
            target_hit = high >= target
        else:  # SELL
            stop_hit = high >= stop
            target_hit = low <= target

        # Handle intrabar breach where both target and stop are reached in the same candle
        if stop_hit and target_hit:
            return self._intrabar_exit(row, side, stop, target)

        if stop_hit:
            return stop, "stop_loss"
        if target_hit:
            return target, "target"

        return None, None

    def _intrabar_exit(self, row: pd.Series, side: str, stop: float, target: float) -> Tuple[float, str]:
        """
        Conservative fallback logic when both SL and TP are hit in the same bar.
        Defaults to trigger Stop Loss to prevent over-optimistic backtests.
        """
        return stop, "stop_loss"

    def _apply_slippage(self, price: float, side: str, is_entry: bool) -> float:
        """Applies unfavorable slippage based on trade direction and action."""
        if (side == "BUY" and is_entry) or (side == "SELL" and not is_entry):
            return price * (1 + self.slippage_rate)
        return price * (1 - self.slippage_rate)

    def _build_trade(self, signal: Any, timestamp: datetime, entry_price: float, quantity: float) -> Trade:
        raw_entry = float(signal.metadata.get("backtest_raw_entry_price") or entry_price)
        return Trade(
            id=f"trade_{timestamp.strftime('%Y%m%d%H%M%S')}",
            symbol=signal.symbol,
            side=signal.side,
            entry_time=timestamp,
            entry_price=entry_price,
            raw_entry_price=raw_entry,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            target=signal.target,
        )

    def _close_trade(self, trade: Trade, timestamp: datetime, raw_exit_price: float, reason: str) -> Trade:
        exit_price = self._apply_slippage(raw_exit_price, trade.side, is_entry=False)
        trade.exit_time = timestamp
        trade.raw_exit_price = raw_exit_price
        trade.exit_price = exit_price
        trade.exit_reason = reason

        # Commission and PnL calculation
        entry_val = trade.entry_price * trade.quantity
        exit_val = trade.exit_price * trade.quantity
        trade.commission = (entry_val + exit_val) * self.commission_rate

        if trade.side == "BUY":
            gross_pnl = (trade.exit_price - trade.entry_price) * trade.quantity
        else:
            gross_pnl = (trade.entry_price - trade.exit_price) * trade.quantity

        trade.pnl = gross_pnl - trade.commission
        trade.pnl_percent = (trade.pnl / entry_val) if entry_val > 0 else 0.0
        trade.slippage = abs(trade.entry_price - trade.raw_entry_price) + abs(trade.exit_price - trade.raw_exit_price)

        return trade

    def _normalize_candles(self, candles: pd.DataFrame) -> pd.DataFrame:
        """Standardizes DataFrame structure and column names."""
        df = candles.copy()
        df.columns = [c.lower() for c in df.columns]
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _calculate_metrics(self, trades: List[Trade], equity_curve: List[float]) -> BacktestMetrics:
        """Generates performance summary metrics from trades and equity curve."""
        if not trades:
            return BacktestMetrics(equity_curve=equity_curve)

        total_trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        total_pnl = sum(t.pnl for t in trades)
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))

        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        max_dd = self._max_drawdown(equity_curve)
        sharpe = self._sharpe_ratio(equity_curve)

        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            equity_curve=equity_curve,
        )

    def _max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculates percentage Peak-to-Trough Maximum Drawdown."""
        arr = np.array(equity_curve)
        peak = np.maximum.accumulate(arr)
        drawdown = (arr - peak) / peak
        return float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    def _sharpe_ratio(self, equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculates annualized Sharpe ratio based on equity returns."""
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        return float(np.sqrt(252) * (np.mean(returns) - risk_free_rate) / np.std(returns))