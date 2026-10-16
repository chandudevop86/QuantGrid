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

    @staticmethod
    def _closed_asof(frame: pd.DataFrame, when: pd.Timestamp, minutes: int) -> pd.DataFrame:
        """Return only candles whose closing time is known at `when`.

        Timestamp is the candle OPEN time, not its close. This deliberately
        prevents historical backtests from observing unfinished HTF candles.
        """
        if frame is None or frame.empty:
            return pd.DataFrame()
        completed = frame["timestamp"] + pd.Timedelta(minutes=minutes) <= when
        return frame.loc[completed].copy()

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        h4 = self._first_frame(context, "h4_candles", "daily_candles", "htf_candles")
        h1 = self._first_frame(context, "h1_candles")
        m15_context = self._first_frame(context, "m15_candles", "mtf_candles")
        entry_timeframe = str(context.params.get("entry_timeframe", "15m")).lower()
        if entry_timeframe not in {"15m", "5m"}:
            return []
        entry_minutes = 5 if entry_timeframe == "5m" else 15
        entries = self._first_frame(context, "m5_candles") if entry_minutes == 5 else m15_context
        entries = entries if entries is not None else (candles if entry_minutes == 15 else None)
        # Never silently substitute lower-timeframe candles for unavailable HTF.
        if h4 is None or h1 is None or entries is None:
            return []
        if entry_minutes == 5 and m15_context is None:
            return []

        signals: list[StrategySignal] = []
        trades_by_session: dict[str, int] = {}
        start_index = max(8, min(20, len(entries) - 1))
        for index in range(start_index, len(entries)):
            row = entries.iloc[index]
            close_time = pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=entry_minutes)
            h4_history = self._closed_asof(h4, close_time, 240)
            h1_history = self._closed_asof(h1, close_time, 60)
            if len(h4_history) < 8 or len(h1_history) < 2:
                continue
            h4_trend = self.trend_analyzer.analyze(h4_history)
            side = h4_trend.side
            if side is None:
                continue
            if entry_minutes == 5:
                m15_history = self._closed_asof(m15_context, close_time, 15)
                m15_trend = self.trend_analyzer.analyze(m15_history)
                if m15_trend.side != side:
                    continue

            h4_zone = self.zone_detector.best_for_side(h4_history, side)
            target_zone = self._opposite_zone(h4_history, side)
            if h4_zone is None or target_zone is None:
                continue
            session = str(row["session_day"])
            if trades_by_session.get(session, 0) >= int(self.config.max_trades_per_day):
                continue
            pullback = self.pullback_detector.detect(h1_history, h4_zone, side)
            if not pullback.pullback_valid:
                continue
            confirmation_score = self._confirmation_score(h1_history, side)
            trigger = self.trigger_detector.detect(entries, index, side)
            if not trigger.valid:
                continue
            volume_confirmed = self._volume_confirmed(row)
            if self.config.require_volume_confirmation and not volume_confirmed:
                continue
            risk = self.risk_manager.build(entries, index, side, target_zone, context.capital, context.risk_pct, self.config.min_rr)
            validation = self.validator.validate(
                trend_aligned=h4_trend.side == side,
                zone_touched=pullback.pullback_valid,
                confirmation_score=confirmation_score,
                trigger_valid=trigger.valid,
                volume_confirmed=volume_confirmed,
                rr=risk.rr,
                countertrend=False,
            )
            if not validation.valid or validation.score < self.config.min_score:
                continue
            metadata = self._metadata(
                h4_trend.to_dict(),
                h4_zone,
                pullback.to_dict(),
                {"score": confirmation_score, "volume_confirmed": volume_confirmed},
                trigger.to_dict(),
                risk.to_dict(),
                validation.to_dict(),
            )
            metadata["entry_timeframe"] = entry_timeframe
            metadata["asof_close_time"] = close_time.isoformat()
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
                metadata=metadata,
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
