from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.smc.amd_phase import AMDPhaseDetector
from Backend.domain.smc.fvg import FVGDetector
from Backend.domain.smc.models import AMDContext, FVGZone, Side, SupplyDemandZone
from Backend.domain.smc.risk import SMCRiskManager
from Backend.domain.smc.scoring import SMCScoringEngine
from Backend.domain.smc.zones import ZoneConfluenceEngine
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class ConfluenceConfig(StrategyConfig):
    range_lookback: int = 18
    distribution_lookback: int = 10
    fvg_max_age_bars: int = 12
    zone_lookback: int = 48
    max_zone_touches: int = 1
    min_atr_pct: float = 0.0008
    min_score: int = 10
    min_rr: float = 2.0
    ideal_rr: float = 3.0
    require_htf_alignment: bool = True
    require_vwap_alignment: bool = True
    require_ema_alignment: bool = True
    require_extreme_entry: bool = True

    @classmethod
    def for_mode(cls, mode: str) -> "ConfluenceConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(
                base,
                range_lookback=24,
                distribution_lookback=8,
                fvg_max_age_bars=10,
                max_zone_touches=0,
                min_atr_pct=0.001,
                min_score=12,
            )
        if normalized == "Aggressive":
            return replace(
                base,
                range_lookback=14,
                distribution_lookback=12,
                fvg_max_age_bars=16,
                min_atr_pct=0.0005,
                min_score=10,
            )
        return base


class AMDStrategy(BaseStrategy):
    name = "AMD + FVG + Supply/Demand"

    def __init__(self, config: ConfluenceConfig | None = None) -> None:
        super().__init__(config or ConfluenceConfig())
        self.config: ConfluenceConfig
        self.signal_builder = SignalBuilder()
        self.indicator_service = IndicatorService()
        self.amd_detector = AMDPhaseDetector()
        self.fvg_detector = FVGDetector(max_age_bars=self.config.fvg_max_age_bars)
        self.zone_engine = ZoneConfluenceEngine(lookback=self.config.zone_lookback, max_touches=self.config.max_zone_touches)
        self.scoring = SMCScoringEngine()
        self.risk = SMCRiskManager()

    def prepare_data(self, data: Any) -> pd.DataFrame:
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        return candles

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        htf_candles = self._prepare_htf(context)
        signals: list[StrategySignal] = []
        traded_sessions: set[str] = set()
        start_index = max(self.config.range_lookback + 3, 20)

        for index in range(start_index, len(candles)):
            row = candles.iloc[index]
            session = str(row["session_day"])
            if session in traded_sessions:
                continue
            if self._low_volatility(row):
                continue

            session_candidate: StrategySignal | None = None
            for side in ("BUY", "SELL"):
                signal = self._evaluate_setup(candles, index, side=side, context=context, htf_candles=htf_candles)
                if signal is None:
                    continue
                if signal.metadata.get("validation_passed") is True:
                    signals.append(signal)
                    traded_sessions.add(session)
                    break
                if session_candidate is None:
                    session_candidate = signal
            if session in traded_sessions:
                continue
            if session_candidate is not None:
                signals.append(session_candidate)
                traded_sessions.add(session)

        return signals

    def _evaluate_setup(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        context: StrategyContext,
        htf_candles: pd.DataFrame | None,
    ) -> StrategySignal | None:
        row = candles.iloc[index]
        amd = self.amd_detector.detect(
            candles,
            index,
            side=side,
            range_lookback=self.config.range_lookback,
            distribution_lookback=self.config.distribution_lookback,
        )
        if amd is None:
            return None
        if self.config.require_extreme_entry and self._is_mid_range_entry(float(row["close"]), amd, side):
            return self._raw_candidate(candles, index, side, context, amd=amd, validation_reason="entry is not in liquidity range extreme")
        if not self._passes_vwap_ema(row, side):
            return self._raw_candidate(candles, index, side, context, amd=amd, validation_reason="vwap or ema alignment rejected setup")

        fvg = self.fvg_detector.find_active_return(candles, index, side, after_index=amd.sweep.sweep_index)
        if fvg is None:
            return self._raw_candidate(candles, index, side, context, amd=amd, validation_reason="no active fvg return after liquidity sweep")
        zone = self.zone_engine.find_zone(candles, index, side, fvg=fvg, after_index=amd.sweep.sweep_index)
        if zone is None:
            return self._raw_candidate(candles, index, side, context, amd=amd, fvg=fvg, validation_reason="no supply or demand zone confluence")
        zone_overlaps_fvg = self.zone_engine.has_confluence(zone, fvg)
        if not zone_overlaps_fvg:
            return self._raw_candidate(candles, index, side, context, amd=amd, fvg=fvg, zone=zone, validation_reason="supply or demand zone does not overlap fvg")

        entry_confirmation = self._entry_confirmation(candles, index, side)
        if entry_confirmation is None:
            return self._raw_candidate(candles, index, side, context, amd=amd, fvg=fvg, zone=zone, validation_reason="missing entry confirmation")

        htf_aligned = self._htf_aligned(htf_candles, row, side)
        if self.config.require_htf_alignment and not htf_aligned:
            return self._raw_candidate(candles, index, side, context, amd=amd, fvg=fvg, zone=zone, validation_reason="higher timeframe alignment rejected setup")

        score = self.scoring.score(
            amd=amd,
            sweep=amd.sweep,
            fvg=fvg,
            zone=zone,
            zone_overlaps_fvg=zone_overlaps_fvg,
            htf_aligned=htf_aligned,
            entry_confirmation=entry_confirmation,
        )
        if score.total < int(self.config.min_score):
            return self._raw_candidate(
                candles,
                index,
                side,
                context,
                amd=amd,
                fvg=fvg,
                zone=zone,
                score_breakdown=score.to_dict(),
                entry_confirmation=entry_confirmation,
                score=score.total,
                validation_reason="score below minimum confirmation threshold",
            )

        stop_loss, target_price = self.risk.levels(
            candles,
            index,
            side=side,
            zone=zone,
            entry=float(row["close"]),
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
            ideal_rr=max(float(context.rr_ratio), float(self.config.ideal_rr)),
        )
        return self.signal_builder.build(
            row,
            strategy_name=self.name,
            symbol=context.symbol,
            side=side,
            capital=context.capital,
            risk_pct=1.0,
            stop_loss=stop_loss,
            target_price=target_price,
            score=score.total,
            metadata={
                **self._metadata(amd, fvg, zone, score.to_dict(), entry_confirmation),
                "raw_setup": True,
                "validation_passed": True,
                "validation_reason": "confirmed AMD FVG supply/demand setup",
            },
        )

    def _raw_candidate(
        self,
        candles: pd.DataFrame,
        index: int,
        side: Side,
        context: StrategyContext,
        *,
        amd: AMDContext,
        validation_reason: str,
        fvg: FVGZone | None = None,
        zone: SupplyDemandZone | None = None,
        score_breakdown: dict[str, Any] | None = None,
        entry_confirmation: str | None = None,
        score: float = 0.0,
    ) -> StrategySignal | None:
        stop_loss, target_price = self._candidate_levels(candles, index, side, context, zone=zone)
        metadata = self._candidate_metadata(
            amd=amd,
            fvg=fvg,
            zone=zone,
            score_breakdown=score_breakdown,
            entry_confirmation=entry_confirmation,
            validation_reason=validation_reason,
        )
        return self.signal_builder.build(
            candles.iloc[index],
            strategy_name=self.name,
            symbol=context.symbol,
            side=side,
            capital=context.capital,
            risk_pct=1.0,
            stop_loss=stop_loss,
            target_price=target_price,
            score=score,
            metadata=metadata,
        )

    def _candidate_levels(
        self,
        candles: pd.DataFrame,
        index: int,
        side: Side,
        context: StrategyContext,
        *,
        zone: SupplyDemandZone | None,
    ) -> tuple[float, float]:
        entry = float(candles.iloc[index]["close"])
        if zone is not None:
            return self.risk.levels(
                candles,
                index,
                side=side,
                zone=zone,
                entry=entry,
                min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
                ideal_rr=max(float(context.rr_ratio), float(self.config.ideal_rr)),
            )
        atr = max(float(candles.iloc[index].get("atr_14", candles.iloc[index].get("avg_range_5", 0.0)) or 0.0), 0.05)
        rr = max(float(context.rr_ratio), float(self.config.min_rr))
        if side == "BUY":
            return entry - atr, entry + atr * rr
        return entry + atr, entry - atr * rr

    def _candidate_metadata(
        self,
        *,
        amd: AMDContext,
        fvg: FVGZone | None,
        zone: SupplyDemandZone | None,
        score_breakdown: dict[str, Any] | None,
        entry_confirmation: str | None,
        validation_reason: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "raw_setup": True,
            "validation_passed": False,
            "validation_reason": validation_reason,
            "amd_phase": amd.phase,
            "liquidity_range": [round(amd.liquidity_range.low, 4), round(amd.liquidity_range.high, 4)],
            "swept_level": round(amd.sweep.swept_level, 4),
            "reason": validation_reason,
            "market_signal": f"{amd.sweep.side} sweep detected; {validation_reason}",
        }
        if fvg is not None:
            metadata["fvg_zone"] = [round(fvg.low, 4), round(fvg.high, 4)]
        if zone is not None:
            metadata["zone_type"] = zone.zone_type
            metadata["zone"] = [round(zone.low, 4), round(zone.high, 4)]
        if score_breakdown is not None:
            metadata["score_breakdown"] = score_breakdown
        if entry_confirmation is not None:
            metadata["entry_confirmation"] = entry_confirmation
        return metadata

    def _metadata(
        self,
        amd: AMDContext,
        fvg: FVGZone,
        zone: SupplyDemandZone,
        score_breakdown: dict[str, Any],
        entry_confirmation: str,
    ) -> dict[str, Any]:
        reason = "; ".join(str(item) for item in score_breakdown["reasons"])
        return {
            "amd_phase": amd.phase,
            "fvg_zone": [round(fvg.low, 4), round(fvg.high, 4)],
            "zone_type": zone.zone_type,
            "zone": [round(zone.low, 4), round(zone.high, 4)],
            "liquidity_range": [round(amd.liquidity_range.low, 4), round(amd.liquidity_range.high, 4)],
            "swept_level": round(amd.sweep.swept_level, 4),
            "entry_confirmation": entry_confirmation,
            "score_breakdown": score_breakdown,
            "reason": reason,
            "market_signal": f"{amd.sweep.side} sweep + FVG return + {zone.zone_type} rejection",
        }

    def _passes_vwap_ema(self, row: pd.Series, side: Side) -> bool:
        close = float(row["close"])
        vwap = float(row["vwap"])
        ema9, ema21, ema50, ema200 = float(row["ema_9"]), float(row["ema_21"]), float(row["ema_50"]), float(row["ema_200"])
        if side == "BUY":
            vwap_ok = close > vwap
            ema_ok = ema9 > ema21 > ema50 > ema200
        else:
            vwap_ok = close < vwap
            ema_ok = ema9 < ema21 < ema50 < ema200
        if self.config.require_vwap_alignment and not vwap_ok:
            return False
        if self.config.require_ema_alignment and not ema_ok:
            return False
        return True

    def _htf_aligned(self, htf_candles: pd.DataFrame | None, ltf_row: pd.Series, side: Side) -> bool:
        row = self._matching_htf_row(htf_candles, ltf_row) if htf_candles is not None else ltf_row
        ema9, ema21, ema50, ema200 = float(row["ema_9"]), float(row["ema_21"]), float(row["ema_50"]), float(row["ema_200"])
        close = float(row["close"])
        if side == "BUY":
            return close > float(row["vwap"]) and ema9 > ema21 > ema50 > ema200
        return close < float(row["vwap"]) and ema9 < ema21 < ema50 < ema200

    @staticmethod
    def _matching_htf_row(htf_candles: pd.DataFrame | None, ltf_row: pd.Series) -> pd.Series:
        if htf_candles is None or htf_candles.empty:
            return ltf_row
        timestamp = pd.Timestamp(ltf_row["timestamp"])
        matches = htf_candles[htf_candles["timestamp"] <= timestamp]
        return matches.iloc[-1] if not matches.empty else htf_candles.iloc[0]

    def _prepare_htf(self, context: StrategyContext) -> pd.DataFrame | None:
        htf_data = context.params.get("htf_candles") or context.params.get("higher_timeframe")
        if htf_data is None:
            return None
        return self.indicator_service.prepare(htf_data)

    @staticmethod
    def _entry_confirmation(candles: pd.DataFrame, index: int, side: Side) -> str | None:
        if index < 1:
            return None
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        bar_range = max(float(row["bar_range"]), 0.01)
        upper_wick = float(row["high"]) - max(float(row["open"]), float(row["close"]))
        lower_wick = min(float(row["open"]), float(row["close"])) - float(row["low"])

        if side == "BUY":
            bullish_close = float(row["close"]) > float(row["open"])
            rejection = bullish_close and lower_wick >= bar_range * 0.35
            engulfing = bullish_close and float(row["close"]) > float(previous["open"]) and float(row["open"]) < float(previous["close"])
        else:
            bearish_close = float(row["close"]) < float(row["open"])
            rejection = bearish_close and upper_wick >= bar_range * 0.35
            engulfing = bearish_close and float(row["close"]) < float(previous["open"]) and float(row["open"]) > float(previous["close"])
        if engulfing:
            return "engulfing"
        if rejection:
            return "rejection"
        return None

    @staticmethod
    def _is_mid_range_entry(entry: float, amd: AMDContext, side: Side) -> bool:
        liquidity_range = amd.liquidity_range
        if liquidity_range.width <= 0:
            return True
        location = (entry - liquidity_range.low) / liquidity_range.width
        if side == "BUY":
            return location > 0.40
        return location < 0.60

    def _low_volatility(self, row: pd.Series) -> bool:
        close = max(float(row["close"]), 0.01)
        atr_pct = float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0) / close
        return atr_pct < float(self.config.min_atr_pct)

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        typed_side: Side = "BUY" if side.upper() == "BUY" else "SELL"
        zone = self.zone_engine.find_zone(candles, index, typed_side)
        if zone is None:
            row = candles.iloc[index]
            entry = float(row["close"])
            atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.05)
            if typed_side == "BUY":
                return entry - atr, entry + atr * max(2.0, float(context.rr_ratio))
            return entry + atr, entry - atr * max(2.0, float(context.rr_ratio))
        return self.risk.levels(
            candles,
            index,
            side=typed_side,
            zone=zone,
            entry=float(candles.iloc[index]["close"]),
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
            ideal_rr=max(float(context.rr_ratio), float(self.config.ideal_rr)),
        )


def run_amd_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: ConfluenceConfig | None = None,
) -> list[StrategySignal]:
    return AMDStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
