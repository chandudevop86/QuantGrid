from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.mtf.entry import LTFEntryConfirmation
from Backend.domain.mtf.htf import HTFTrendAnalyzer
from Backend.domain.mtf.models import HTFTrend, LTFEntry, PullbackSetup, Side
from Backend.domain.mtf.risk import MTFRiskManager
from Backend.domain.mtf.scoring import MTFScoringEngine
from Backend.domain.mtf.setup import MTFSetupDetector
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class MTFConfig(StrategyConfig):
    htf_timeframe: str = "15m"
    mtf_timeframe: str = "5m"
    max_trades_per_day: int = 2
    cooldown_minutes: int = 15
    min_atr_pct: float = 0.0007
    min_score: int = 6
    min_rr: float = 2.0
    require_htf_structure: bool = True

    @classmethod
    def for_mode(cls, mode: str) -> "MTFConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, min_score=7, min_atr_pct=0.001, cooldown_minutes=20)
        if normalized == "Aggressive":
            return replace(base, min_score=6, min_atr_pct=0.0005, require_htf_structure=False)
        return base


class MTFStrategy(BaseStrategy):
    name = "MTF"

    def __init__(self, config: MTFConfig | None = None) -> None:
        super().__init__(config or MTFConfig())
        self.config: MTFConfig
        self.indicator_service = IndicatorService()
        self.htf = HTFTrendAnalyzer(self.indicator_service)
        self.setup = MTFSetupDetector()
        self.entry = LTFEntryConfirmation()
        self.scoring = MTFScoringEngine()
        self.risk = MTFRiskManager()
        self.signal_builder = SignalBuilder()

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        htf_candles = self.htf.prepare(context.params.get("htf_candles") or context.params.get("higher_timeframe"))
        mtf_candles = self._prepare_mtf(context.params.get("mtf_candles") or context.params.get("mid_timeframe"))
        signals: list[StrategySignal] = []
        trade_count_by_session: dict[str, int] = {}
        last_trade_time: pd.Timestamp | None = None

        for index in range(20, len(candles)):
            row = candles.iloc[index]
            session = str(row["session_day"])
            timestamp = pd.Timestamp(row["timestamp"])
            if trade_count_by_session.get(session, 0) >= int(self.config.max_trades_per_day):
                continue
            if last_trade_time is not None and timestamp - last_trade_time < timedelta(minutes=int(self.config.cooldown_minutes)):
                continue
            if self._low_volatility(row):
                continue

            signal = self._evaluate(candles, index, context=context, htf_candles=htf_candles, mtf_candles=mtf_candles)
            if signal is None:
                continue
            signals.append(signal)
            trade_count_by_session[session] = trade_count_by_session.get(session, 0) + 1
            last_trade_time = timestamp

        return signals

    def _evaluate(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        context: StrategyContext,
        htf_candles: pd.DataFrame | None,
        mtf_candles: pd.DataFrame | None,
    ) -> StrategySignal | None:
        row = candles.iloc[index]
        htf_trend = self.htf.analyze_at(htf_candles, row)
        side = htf_trend.side
        if side is None:
            return None
        if self.config.require_htf_structure and not htf_trend.structure_confirmed:
            return None

        setup = self.setup.detect(mtf_candles, row, side)
        if setup is None:
            return None
        entry = self.entry.confirm(candles, index, side)
        if entry is None:
            return None
        momentum_ok = self.scoring.momentum_confirmed(candles, index, side)
        score = self.scoring.score(htf=htf_trend, setup=setup, entry=entry, momentum_confirmed=momentum_ok, side=side)
        if score.total < int(self.config.min_score):
            return None

        stop_loss, target = self.risk.levels(
            candles,
            index,
            side=side,
            entry=float(row["close"]),
            htf=htf_trend,
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
        )
        return self.signal_builder.build(
            row,
            strategy_name=self.name,
            symbol=context.symbol,
            side=side,
            capital=context.capital,
            risk_pct=1.0,
            stop_loss=stop_loss,
            target_price=target,
            score=score.total,
            metadata=self._metadata(htf_trend, setup, entry, score.to_dict()),
        )

    def _metadata(
        self,
        htf_trend: HTFTrend,
        setup: PullbackSetup,
        entry: LTFEntry,
        score_breakdown: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "htf_bias": htf_trend.bias,
            "htf_structure_confirmed": htf_trend.structure_confirmed,
            "htf_structure_level": round(htf_trend.structure_level, 4) if htf_trend.structure_level is not None else None,
            "pullback": {
                "touched_ema21": setup.touched_ema21,
                "touched_vwap": setup.touched_vwap,
                "quality": setup.quality,
            },
            "entry_confirmation": entry.kind,
            "score_breakdown": score_breakdown,
            "reason": "; ".join(str(item) for item in score_breakdown["reasons"]),
            "market_signal": f"{htf_trend.bias} HTF + 5m pullback + 1m {entry.kind}",
        }

    def _prepare_mtf(self, mtf_data: Any | None) -> pd.DataFrame | None:
        if mtf_data is None:
            return None
        prepared = self.indicator_service.prepare(mtf_data)
        return prepared if not prepared.empty else None

    def _low_volatility(self, row: pd.Series) -> bool:
        close = max(float(row["close"]), 0.01)
        atr_pct = float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0) / close
        return atr_pct < float(self.config.min_atr_pct)

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        typed_side: Side = "BUY" if side.upper() == "BUY" else "SELL"
        row = candles.iloc[index]
        fallback_htf = HTFTrend("bullish" if typed_side == "BUY" else "bearish", True, False, 0.0, None, "fallback")
        return self.risk.levels(
            candles,
            index,
            side=typed_side,
            entry=float(row["close"]),
            htf=fallback_htf,
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
        )


def run_mtf_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: MTFConfig | None = None,
) -> list[StrategySignal]:
    return MTFStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
