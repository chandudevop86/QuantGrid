from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

import pandas as pd

from Backend.domain.crt_tbs.crt import CRTDetector
from Backend.domain.crt_tbs.liquidity import LiquiditySweep, LiquiditySweepDetector
from Backend.domain.crt_tbs.mtf import MultiTimeframeAnalyzer
from Backend.domain.crt_tbs.tbs import TBSDetector, TBSSetup
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class CRTTBSConfig(StrategyConfig):
    liquidity_lookback: int = 20
    crt_lookback: int = 14
    min_score: int = 5
    min_trade_score: int = 7
    min_rr: float = 2.0
    target2_rr: float = 3.0
    max_signal_age_minutes: int = 45
    require_htf_alignment: bool = True

    @classmethod
    def for_mode(cls, mode: str) -> "CRTTBSConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, min_trade_score=9, require_htf_alignment=True)
        if normalized == "Aggressive":
            return replace(base, min_trade_score=5, require_htf_alignment=False)
        return base


class CRTTBSStrategy(BaseStrategy):
    name = "CRT TBS"

    def __init__(self, config: CRTTBSConfig | None = None) -> None:
        super().__init__(config or CRTTBSConfig())
        self.config: CRTTBSConfig
        self.crt_detector = CRTDetector(lookback=self.config.crt_lookback)
        self.liquidity_detector = LiquiditySweepDetector(lookback=self.config.liquidity_lookback)
        self.tbs_detector = TBSDetector(range_lookback=self.config.liquidity_lookback)
        self.mtf_analyzer = MultiTimeframeAnalyzer()
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data: Any) -> pd.DataFrame:
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        out = candles.copy()
        out["previous_close"] = out["close"].shift(1)
        out["avg_volume_20"] = out["volume"].fillna(0.0).rolling(20, min_periods=3).mean()
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        traded_sessions: set[tuple[str, str]] = set()
        start_index = max(self.config.liquidity_lookback, self.config.crt_lookback) + 2
        latest_timestamp = pd.Timestamp(candles.iloc[-1]["timestamp"]) if not candles.empty else None

        for index in range(start_index, len(candles)):
            row = candles.iloc[index]
            timestamp = pd.Timestamp(row["timestamp"])
            session = str(row["session_day"])
            if latest_timestamp is not None and latest_timestamp - timestamp > timedelta(minutes=self.config.max_signal_age_minutes):
                continue

            sweeps = self.liquidity_detector.detect(candles, index)
            if not sweeps:
                continue
            crt = self.crt_detector.find_recent(candles, index)
            if crt is None:
                continue

            for sweep in sweeps:
                side = self.crt_detector.setup_direction(crt, row, sweep)
                if side is None or (session, side) in traded_sessions:
                    continue

                tbs = self.tbs_detector.detect(candles, index, sweep)
                mtf = self.mtf_analyzer.analyze(context.params, side, candles.iloc[: index + 1])
                volume_confirmed = self._volume_confirmed(row)
                score, reasons = self._score(
                    crt_present=True,
                    sweep=sweep,
                    tbs=tbs,
                    htf_aligned=mtf.aligned,
                    volume_confirmed=volume_confirmed,
                )
                if score < self.config.min_score:
                    continue
                if self.config.require_htf_alignment and not mtf.aligned:
                    continue

                stop_loss, target1, target2 = self._risk_levels(row, side, sweep, crt, tbs, context)
                rr = self._risk_reward(float(row["close"]), stop_loss, target1)
                if rr < max(float(context.rr_ratio), float(self.config.min_rr)):
                    continue
                if score < self.config.min_trade_score:
                    continue

                setup_type = self.crt_detector.setup_type(crt, row, side)
                signal = self.signal_builder.build(
                    row,
                    strategy_name=self.name,
                    symbol=context.symbol,
                    side=side,
                    capital=context.capital,
                    risk_pct=context.risk_pct,
                    stop_loss=stop_loss,
                    target_price=target1,
                    score=score,
                    metadata=self._metadata(
                        crt=crt.to_dict(),
                        sweep=sweep,
                        tbs=tbs,
                        setup_type=setup_type,
                        target1=target1,
                        target2=target2,
                        rr=rr,
                        score=score,
                        reasons=reasons,
                        mtf=mtf.to_dict(),
                        volume_confirmed=volume_confirmed,
                    ),
                )
                if signal is None:
                    continue
                signals.append(signal)
                traded_sessions.add((session, side))

        return signals

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        sweep = self.liquidity_detector.detect_primary(candles, index, side)
        crt = self.crt_detector.find_recent(candles, index)
        if sweep is None or crt is None:
            atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.05)
            close = float(row["close"])
            if side.upper() == "BUY":
                return close - atr, close + atr * max(float(context.rr_ratio), self.config.min_rr)
            return close + atr, close - atr * max(float(context.rr_ratio), self.config.min_rr)
        tbs = self.tbs_detector.detect(candles, index, sweep)
        stop, target1, _target2 = self._risk_levels(row, side, sweep, crt, tbs, context)
        return stop, target1

    def _risk_levels(
        self,
        row: pd.Series,
        side: str,
        sweep: LiquiditySweep,
        crt: Any,
        tbs: TBSSetup | None,
        context: StrategyContext,
    ) -> tuple[float, float, float]:
        entry = float(row["close"])
        atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), max(entry * 0.001, 0.05))
        rr1 = max(float(context.rr_ratio), float(self.config.min_rr))
        rr2 = max(float(self.config.target2_rr), rr1)
        if tbs is not None:
            stop = float(tbs.stop_loss)
        elif side.upper() == "BUY":
            stop = min(float(sweep.level), float(crt.low), float(row["low"])) - atr * 0.2
        else:
            stop = max(float(sweep.level), float(crt.high), float(row["high"])) + atr * 0.2
        risk = max(abs(entry - stop), atr * 0.25)
        if side.upper() == "BUY":
            return stop, entry + risk * rr1, entry + risk * rr2
        return stop, entry - risk * rr1, entry - risk * rr2

    @staticmethod
    def _risk_reward(entry: float, stop: float, target: float) -> float:
        risk = abs(float(entry) - float(stop))
        return abs(float(target) - float(entry)) / risk if risk > 0 else 0.0

    @staticmethod
    def _volume_confirmed(row: pd.Series) -> bool:
        volume = float(row.get("volume", 0.0) or 0.0)
        average = float(row.get("avg_volume_20", 0.0) or 0.0)
        return average > 0 and volume >= average * 1.05

    @staticmethod
    def _score(
        *,
        crt_present: bool,
        sweep: LiquiditySweep | None,
        tbs: TBSSetup | None,
        htf_aligned: bool,
        volume_confirmed: bool,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        if crt_present:
            score += 3
            reasons.append("CRT present")
        if sweep is not None and sweep.swept:
            score += 3
            reasons.append(f"{sweep.type} liquidity sweep")
        if tbs is not None:
            score += 2
            reasons.append(f"TBS confirmation: {tbs.trap_type}")
        if htf_aligned:
            score += 2
            reasons.append("HTF alignment")
        if volume_confirmed:
            score += 1
            reasons.append("Volume confirmation")
        return score, reasons

    @staticmethod
    def _quality_tier(score: int) -> str:
        if score >= 10:
            return "HIGH QUALITY"
        if score >= 7:
            return "MEDIUM QUALITY"
        if score >= 5:
            return "WATCHLIST"
        return "REJECTED"

    def _metadata(
        self,
        *,
        crt: dict[str, Any],
        sweep: LiquiditySweep,
        tbs: TBSSetup | None,
        setup_type: str,
        target1: float,
        target2: float,
        rr: float,
        score: int,
        reasons: list[str],
        mtf: dict[str, Any],
        volume_confirmed: bool,
    ) -> dict[str, Any]:
        trap_type = tbs.trap_type if tbs is not None else ("bear_trap" if sweep.type == "SSL" else "bull_trap")
        quality = self._quality_tier(score)
        return {
            "strategy_key": "crt_tbs",
            "setup_type": setup_type,
            "best_setup_type": f"{setup_type} + {trap_type}",
            "crt_range": crt,
            "liquidity_sweep": sweep.to_dict(),
            "sweep_type": sweep.type,
            "swept_level": round(float(sweep.level), 4),
            "trap_type": trap_type,
            "tbs": tbs.to_dict() if tbs is not None else None,
            "entry_zone": tbs.to_dict()["entry_zone"] if tbs is not None else [crt["low"], crt["high"]],
            "target_1": round(float(target1), 4),
            "target_2": round(float(target2), 4),
            "risk_reward": round(float(rr), 2),
            "rr_ratio": round(float(rr), 2),
            "quality_tier": quality,
            "signal_quality": quality,
            "score_breakdown": {"total": score, "max": 11, "reasons": reasons},
            "htf_bias": mtf.get("bias"),
            "mtf": mtf,
            "volume_confirmation": volume_confirmed,
            "zone_type": "demand liquidity zone" if sweep.type == "SSL" else "supply liquidity zone",
            "entry_confirmation": "rejection + re-entry",
            "reason": "; ".join(reasons),
            "market_signal": f"{quality}: {sweep.type} sweep, {trap_type}, {setup_type}",
        }


def run_crt_tbs_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: CRTTBSConfig | None = None,
) -> list[StrategySignal]:
    return CRTTBSStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
