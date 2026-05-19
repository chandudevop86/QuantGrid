from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from Backend.domain.btst.eod import EODConfirmationEngine
from Backend.domain.btst.gap import GapProbabilityFilter
from Backend.domain.btst.models import EODConfirmation, GapAssessment, Side, SwingStructure
from Backend.domain.btst.risk import BTSTRiskManager
from Backend.domain.btst.scoring import BTSTScoringEngine
from Backend.domain.btst.structure import SwingStructureDetector
from Backend.domain.btst.validator import BTSTSignalValidator
from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class BTSTConfig(StrategyConfig):
    close_window_minutes: int = 30
    min_score: int = 6
    min_atr_pct: float = 0.001
    min_rr: float = 2.0
    max_trades_per_day: int = 1
    close_strength_threshold: float = 0.75

    @classmethod
    def for_mode(cls, mode: str) -> "BTSTConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, min_score=7, min_atr_pct=0.0012, close_strength_threshold=0.82)
        if normalized == "Aggressive":
            return replace(base, min_score=6, min_atr_pct=0.0008, close_strength_threshold=0.70)
        return base


class BTSTStrategy(BaseStrategy):
    name = "BTST"

    def __init__(self, config: BTSTConfig | None = None) -> None:
        super().__init__(config or BTSTConfig())
        self.config: BTSTConfig
        self.indicator_service = IndicatorService()
        self.structure = SwingStructureDetector()
        self.eod = EODConfirmationEngine(
            close_window_minutes=self.config.close_window_minutes,
            close_strength_threshold=self.config.close_strength_threshold,
        )
        self.gap = GapProbabilityFilter()
        self.scoring = BTSTScoringEngine()
        self.risk = BTSTRiskManager()
        self.validator = BTSTSignalValidator(min_atr_pct=self.config.min_atr_pct, min_score=self.config.min_score)
        self.signal_builder = SignalBuilder()

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        structure_frame = self._prepare_structure_frame(candles, context)
        signals: list[StrategySignal] = []
        traded_days: set[str] = set()

        for index in range(30, len(candles)):
            row = candles.iloc[index]
            session = str(row["session_day"])
            if session in traded_days:
                continue

            structure_index = self._matching_index(structure_frame, row)
            structure = self.structure.detect(structure_frame, structure_index)
            side = structure.side
            if side is None:
                continue
            valid_market, _ = self.validator.valid_market(row, structure, side)
            if not valid_market:
                continue

            eod = self.eod.confirm(candles, index, side)
            if eod is None:
                continue
            if not self.scoring.momentum_confirmed(row, side) or not self.scoring.vwap_aligned(row, side):
                continue

            gap = self.gap.assess(row, side=side, structure=structure, eod=eod)
            score = self.scoring.score(row=row, side=side, structure=structure, eod=eod)
            valid_signal, _ = self.validator.valid_signal(score=score.total, gap=gap)
            if not valid_signal:
                continue

            stop_loss, target = self.risk.levels(
                candles,
                index,
                side=side,
                entry=float(row["close"]),
                eod=eod,
                structure=structure,
                min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
            )
            signal = self.signal_builder.build(
                row,
                strategy_name=self.name,
                symbol=context.symbol,
                side=side,
                capital=context.capital,
                risk_pct=1.0,
                stop_loss=stop_loss,
                target_price=target,
                score=score.total,
                metadata=self._metadata(structure, eod, gap, score.to_dict()),
            )
            if signal is None:
                continue
            signals.append(signal)
            traded_days.add(session)

        return signals

    def _prepare_structure_frame(self, candles: pd.DataFrame, context: StrategyContext) -> pd.DataFrame:
        for key in ("daily_candles", "eod_candles", "htf_candles", "higher_timeframe"):
            data = context.params.get(key)
            if data is not None:
                prepared = self.indicator_service.prepare(data)
                if not prepared.empty:
                    return prepared
        return candles

    @staticmethod
    def _matching_index(frame: pd.DataFrame, row: pd.Series) -> int:
        timestamp = pd.Timestamp(row["timestamp"])
        matches = frame[frame["timestamp"] <= timestamp]
        if matches.empty:
            return 0
        return int(matches.index[-1])

    def _metadata(
        self,
        structure: SwingStructure,
        eod: EODConfirmation,
        gap: GapAssessment,
        score_breakdown: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "btst": True,
            "trend": structure.trend,
            "structure_breakout": structure.breakout_confirmed,
            "day_high": round(eod.day_high, 4),
            "day_low": round(eod.day_low, 4),
            "close_strength": round(eod.close_strength, 3),
            "gap_probability_score": gap.probability_score,
            "score_breakdown": score_breakdown,
            "reason": "; ".join(str(item) for item in score_breakdown["reasons"] + [gap.reason]),
            "market_signal": f"{structure.trend} EOD breakout BTST/STBT",
        }

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        typed_side: Side = "BUY" if side.upper() == "BUY" else "SELL"
        row = candles.iloc[index]
        eod = self.eod.confirm(candles, index, typed_side)
        structure = self.structure.detect(candles, index)
        if eod is None:
            session = str(row["session_day"])
            session_frame = candles[candles["session_day"] == session].iloc[: index + 1]
            day_high = float(session_frame["high"].max())
            day_low = float(session_frame["low"].min())
            eod = EODConfirmation(typed_side, True, 1.0, day_high, day_low, "fallback EOD levels")
        return self.risk.levels(
            candles,
            index,
            side=typed_side,
            entry=float(row["close"]),
            eod=eod,
            structure=structure,
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
        )


def run_btst_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: BTSTConfig | None = None,
) -> list[StrategySignal]:
    return BTSTStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
