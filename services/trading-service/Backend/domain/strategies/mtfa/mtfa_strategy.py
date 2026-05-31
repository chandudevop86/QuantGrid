from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder
from Backend.domain.strategies.mtfa.mtfa_validator import MTFAValidator
from Backend.domain.strategies.mtfa.pullback_detector import PullbackDetector
from Backend.domain.strategies.mtfa.risk_manager import MTFARiskManager
from Backend.domain.strategies.mtfa.trend_analyzer import TrendAnalyzer
from Backend.domain.strategies.mtfa.trigger_detector import TriggerDetector
from Backend.domain.strategies.mtfa.zone_detector import MTFAZone, ZoneDetector


@dataclass(slots=True)
class MTFAConfig(StrategyConfig):
    min_score: int = 7
    min_rr: float = 2.0
    preferred_rr: float = 3.0
    max_trades_per_day: int = 2
    require_volume_confirmation: bool = False

    @classmethod
    def for_mode(cls, mode: str) -> "MTFAConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, min_score=9, require_volume_confirmation=True)
        if normalized == "Aggressive":
            return replace(base, min_score=7, require_volume_confirmation=False)
        return base


class MTFAStrategy(BaseStrategy):
    name = "MTFA"

    def __init__(self, config: MTFAConfig | None = None) -> None:
        super().__init__(config or MTFAConfig())
        self.config: MTFAConfig
        self.indicator_service = IndicatorService()
        self.trend_analyzer = TrendAnalyzer()
        self.zone_detector = ZoneDetector()
        self.pullback_detector = PullbackDetector()
        self.trigger_detector = TriggerDetector()
        self.risk_manager = MTFARiskManager()
        self.validator = MTFAValidator()
        self.signal_builder = SignalBuilder()

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        h4 = self._first_frame(context, "h4_candles", "daily_candles", "htf_candles")
        h1 = self._first_frame(context, "h1_candles", "htf_candles")
        m15 = self._first_frame(context, "m15_candles", "mtf_candles", "m5_candles")
        h4 = h4 if h4 is not None else candles
        h1 = h1 if h1 is not None else candles
        m15 = m15 if m15 is not None else candles
        h4_trend = self.trend_analyzer.analyze(h4)
        side = h4_trend.side
        if side is None:
            return []
        h4_zone = self.zone_detector.best_for_side(h4, side)
        target_zone = self._opposite_zone(h4, side)
        if h4_zone is None or target_zone is None:
            return []

        signals: list[StrategySignal] = []
        trades_by_session: dict[str, int] = {}
        start_index = max(8, min(20, len(m15) - 1))
        for index in range(start_index, len(m15)):
            row = m15.iloc[index]
            session = str(row["session_day"])
            if trades_by_session.get(session, 0) >= int(self.config.max_trades_per_day):
                continue
            pullback = self.pullback_detector.detect(h1, h4_zone, side)
            if not pullback.pullback_valid:
                continue
            confirmation_score = self._confirmation_score(h1, side)
            trigger = self.trigger_detector.detect(m15, index, side)
            if not trigger.valid:
                continue
            volume_confirmed = self._volume_confirmed(row)
            if self.config.require_volume_confirmation and not volume_confirmed:
                continue
            risk = self.risk_manager.build(m15, index, side, target_zone, context.capital, context.risk_pct, self.config.min_rr)
            countertrend = (side == "BUY" and h4_trend.trend == "DOWNTREND") or (side == "SELL" and h4_trend.trend == "UPTREND")
            validation = self.validator.validate(
                trend_aligned=True,
                zone_touched=True,
                confirmation_score=confirmation_score,
                trigger_valid=trigger.valid,
                volume_confirmed=volume_confirmed,
                rr=risk.rr,
                countertrend=countertrend,
            )
            if not validation.valid or validation.score < self.config.min_score:
                continue
            signal = self.signal_builder.build(
                row,
                strategy_name=self.name,
                symbol=context.symbol,
                side=side,
                capital=context.capital,
                risk_pct=context.risk_pct,
                stop_loss=risk.stop_loss,
                target_price=risk.target,
                score=validation.score,
                metadata=self._metadata(
                    h4_trend.to_dict(),
                    h4_zone,
                    pullback.to_dict(),
                    {"score": confirmation_score, "volume_confirmed": volume_confirmed},
                    trigger.to_dict(),
                    risk.to_dict(),
                    validation.to_dict(),
                ),
            )
            if signal is None:
                continue
            signals.append(signal)
            trades_by_session[session] = trades_by_session.get(session, 0) + 1
        return signals

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        zone = self._opposite_zone(candles, side)
        if zone is None:
            row = candles.iloc[index]
            entry = float(row["close"])
            atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.05)
            if side.upper() == "BUY":
                return entry - atr, entry + atr * max(2.0, float(context.rr_ratio))
            return entry + atr, entry - atr * max(2.0, float(context.rr_ratio))
        risk = self.risk_manager.build(candles, index, side, zone, context.capital, context.risk_pct, self.config.min_rr)
        return risk.stop_loss, risk.target

    def _prepare_optional(self, data: Any) -> pd.DataFrame | None:
        if data is None:
            return None
        frame = self.indicator_service.prepare(data)
        return frame if not frame.empty else None

    def _first_frame(self, context: StrategyContext, *keys: str) -> pd.DataFrame | None:
        for key in keys:
            frame = self._prepare_optional(context.params.get(key))
            if frame is not None:
                return frame
        return None

    def _opposite_zone(self, candles: pd.DataFrame, side: str) -> MTFAZone | None:
        opposite = "SELL" if side.upper() == "BUY" else "BUY"
        return self.zone_detector.best_for_side(candles, opposite)

    @staticmethod
    def _confirmation_score(candles: pd.DataFrame, side: str) -> int:
        if len(candles) < 2:
            return 0
        row = candles.iloc[-1]
        previous = candles.iloc[-2]
        score = 0
        if side.upper() == "BUY":
            engulfing = float(row["close"]) > float(row["open"]) and float(row["close"]) > float(previous["open"]) and float(row["open"]) <= float(previous["close"])
            pin = (min(float(row["open"]), float(row["close"])) - float(row["low"])) / max(float(row["bar_range"]), 0.01) >= 0.35
        else:
            engulfing = float(row["close"]) < float(row["open"]) and float(row["close"]) < float(previous["open"]) and float(row["open"]) >= float(previous["close"])
            pin = (float(row["high"]) - max(float(row["open"]), float(row["close"]))) / max(float(row["bar_range"]), 0.01) >= 0.35
        inside = float(row["high"]) <= float(previous["high"]) and float(row["low"]) >= float(previous["low"])
        if engulfing:
            score += 2
        if pin:
            score += 1
        if inside:
            score += 1
        return min(score, 3)

    @staticmethod
    def _volume_confirmed(row: pd.Series) -> bool:
        volume = float(row.get("volume", 0.0) or 0.0)
        avg_volume = float(row.get("avg_volume_5", 0.0) or 0.0)
        return avg_volume > 0 and volume >= avg_volume * 1.05

    @staticmethod
    def _metadata(
        h4_trend: dict[str, Any],
        h4_zone: MTFAZone,
        pullback: dict[str, Any],
        confirmation: dict[str, Any],
        trigger: dict[str, Any],
        risk: dict[str, Any],
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "strategy_key": "mtfa",
            "mtfa_valid": validation["valid"],
            "mtfa_4h_trend": h4_trend["trend"],
            "mtfa_4h_zone": h4_zone.to_dict(),
            "mtfa_1h_pullback": pullback,
            "mtfa_1h_confirmation": confirmation,
            "mtfa_15m_trigger": trigger,
            "mtfa": {
                "h4_trend": h4_trend,
                "h4_zone": h4_zone.to_dict(),
                "h1_pullback": pullback,
                "h1_confirmation": confirmation,
                "m15_trigger": trigger,
                "risk": risk,
                "validation": validation,
            },
            "quality_grade": validation["grade"],
            "mtfa_grade": validation["grade"],
            "mtfa_score": validation["score"],
            "signal_quality": validation["grade"],
            "risk_reward": risk["rr"],
            "rr_ratio": risk["rr"],
            "position_size": risk["position_size"],
            "risk_amount": risk["risk_amount"],
            "score_breakdown": {"total": validation["score"], "max": 12, "reasons": validation["reasons"]},
            "reason": "; ".join(validation["reasons"]),
            "market_signal": f"MTFA {h4_trend['trend']} + {h4_zone.zone_type} + {trigger['trigger_type']}",
        }


def run_mtfa_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: MTFAConfig | None = None,
) -> list[StrategySignal]:
    return MTFAStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
