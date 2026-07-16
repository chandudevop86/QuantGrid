from __future__ import annotations

from typing import Any

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestResult, BacktestTrade
from Backend.trading_system.backtesting import BacktestEngine as CanonicalBacktestEngine


class BacktestEngine:
    """Compatibility adapter over the canonical trading-system simulator.

    The app API historically exposed a different trade/result schema. Keep that
    contract here, but do not maintain a second fill or trade simulation engine.
    """

    def __init__(self, service: Any | None = None, **engine_kwargs: Any) -> None:
        # ``service`` remains accepted for backwards compatibility with callers
        # that previously injected TradingService into the legacy simulator.
        self.service = service
        self.engine = CanonicalBacktestEngine(**engine_kwargs)

    def run(
        self,
        *,
        strategy: str,
        symbol: str,
        candles: list[dict[str, Any]],
        capital: float = 100_000,
        risk_pct: float = 2.0,
        rr_ratio: float = 2.0,
    ) -> BacktestResult:
        canonical = self.engine.run(
            candles=candles,
            strategy_name=strategy,
            symbol=symbol,
            capital=capital,
            risk_pct=risk_pct,
            rr_ratio=rr_ratio,
            min_score=0.0,
        )
        trades = [self._compatibility_trade(item) for item in canonical.trades]
        metrics = calculate_metrics(trades)
        metrics["rejected_signal_count"] = canonical.rejected_signal_count
        metrics["rejection_reasons"] = dict(canonical.rejection_reasons)
        metrics["simulation_engine"] = "canonical_trading_system"
        metrics["synthetic_trade_fallback"] = False
        return BacktestResult(strategy=strategy, symbol=symbol.upper(), metrics=metrics, trades=trades)

    @staticmethod
    def _compatibility_trade(item: dict[str, Any]) -> BacktestTrade:
        pnl = float(item.get("pnl") or 0.0)
        metadata = dict(item.get("metadata") or {})
        metadata.update(
            {
                "gross_pnl": item.get("gross_pnl", pnl),
                "total_costs": item.get("total_costs", 0.0),
                "slippage_cost": item.get("slippage_cost", 0.0),
                "brokerage": item.get("brokerage", 0.0),
                "taxes": item.get("taxes", 0.0),
                "latency_ms": item.get("latency_ms", 0),
                "exit_reason": item.get("exit_reason"),
            }
        )
        return BacktestTrade(
            strategy=str(item.get("strategy_name") or "unknown"),
            symbol=str(item.get("symbol") or "unknown").upper(),
            side=str(item.get("side") or "BUY").upper(),
            entry=float(item.get("entry_price") or 0.0),
            stop_loss=float(item.get("stop_loss") or 0.0),
            target=float(item.get("target_price") or 0.0),
            quantity=int(item.get("quantity") or 0),
            entry_time=str(item.get("entry_time") or ""),
            exit_time=str(item.get("exit_time") or ""),
            exit_price=float(item.get("exit_price") or 0.0),
            pnl=pnl,
            rr=float(item.get("rr") or 0.0),
            outcome="win" if pnl > 0 else "loss" if pnl < 0 else "flat",
            metadata=metadata,
        )
