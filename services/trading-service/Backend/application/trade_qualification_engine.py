from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd

from Backend.application.candle_validation import normalize_timestamp, validate_live_candle
from Backend.application.paper_trade_store import risk_status
from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.signal import StrategySignal


MarketContext = Literal["UPTREND", "DOWNTREND", "RANGE"]
VolatilityRegime = Literal["LOW", "NORMAL", "HIGH"]


@dataclass(frozen=True, slots=True)
class PositionSizing:
    capital: float
    risk_pct: float
    risk_amount: float
    position_size: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TradeQualification:
    allowed: bool
    reason: str
    score: int
    max_score: int
    quality_grade: str
    market_context: MarketContext
    trend: str
    trend_aligned: bool
    support_resistance: dict[str, Any]
    volume_status: str
    volatility_status: VolatilityRegime
    rr: float
    position_sizing: PositionSizing
    checks: dict[str, Any]
    score_breakdown: dict[str, int]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["position_sizing"] = self.position_sizing.to_dict()
        return payload


class TradeQualificationEngine:
    MAX_SCORE = 12

    def __init__(self, indicators: IndicatorService | None = None) -> None:
        self.indicators = indicators or IndicatorService()

    def qualify(
        self,
        signal: StrategySignal,
        *,
        candles: list[dict[str, Any]] | pd.DataFrame,
        capital: float = 100_000,
        risk_pct: float = 1.0,
        h4_candles: list[dict[str, Any]] | pd.DataFrame | None = None,
        h1_candles: list[dict[str, Any]] | pd.DataFrame | None = None,
        m15_candles: list[dict[str, Any]] | pd.DataFrame | None = None,
        enforce_execution_checks: bool = False,
        execution_mode: str = "paper",
    ) -> TradeQualification:
        frame = self._prepare(candles)
        if frame.empty:
            return self._empty(signal, capital, risk_pct, "NO_CANDLES")

        row = self._row_for_signal(frame, signal)
        h4 = self._prepare_optional(h4_candles)
        h1 = self._prepare_optional(h1_candles)
        m15 = self._prepare_optional(m15_candles)
        context = self._market_context(frame)
        sr = self._support_resistance(frame, row, signal.side)
        trends = {
            "h4": self._trend(h4) if h4 is not None else self._trend(frame),
            "h1": self._trend(h1) if h1 is not None else self._trend(frame),
            "m15": self._trend(m15) if m15 is not None else self._trend(frame),
        }
        trend_aligned = self._trend_aligned(signal.side, trends)
        volume_score, volume_status = self._volume_score(row, signal)
        volatility_score, volatility_status, volatility_reject = self._volatility_score(row)
        indicator_score, indicator_notes = self._indicator_score(row, signal.side)
        rr = self._risk_reward(signal)
        sizing = self._position_size(signal, capital, risk_pct)

        score_breakdown = {
            "trend_alignment": 2 if trend_aligned else 0,
            "support_resistance": 2 if sr["aligned"] else 0,
            "volume": max(0, min(2, volume_score)),
            "volatility": volatility_score,
            "indicators": indicator_score,
            "risk_reward": 2 if rr >= 2.0 else 0,
        }
        score = int(sum(score_breakdown.values()))
        grade = self._grade(score)
        notes = [*indicator_notes]
        hard_reasons: list[str] = []

        if not trend_aligned and score < 11:
            hard_reasons.append("COUNTERTREND_SETUP")
        if volume_score < 0:
            hard_reasons.append(volume_status.upper().replace(" ", "_"))
        if volatility_reject:
            hard_reasons.append(f"VOLATILITY_{volatility_status}")
        if rr < 2.0:
            hard_reasons.append("RR_BELOW_2")
        if score < 5:
            hard_reasons.append("TQE_SCORE_REJECTED")

        checks = self._execution_checks(frame, signal, execution_mode) if enforce_execution_checks else {}
        if enforce_execution_checks:
            failed = [name for name, value in checks.items() if value is False]
            hard_reasons.extend(f"EXECUTION_CHECK_FAILED:{name}" for name in failed)

        allowed = not hard_reasons
        return TradeQualification(
            allowed=allowed,
            reason="OK" if allowed else hard_reasons[0],
            score=score,
            max_score=self.MAX_SCORE,
            quality_grade=grade,
            market_context=context,
            trend=trends["h1"],
            trend_aligned=trend_aligned,
            support_resistance=sr,
            volume_status=volume_status,
            volatility_status=volatility_status,
            rr=round(rr, 2),
            position_sizing=sizing,
            checks=checks,
            score_breakdown=score_breakdown,
            notes=notes + hard_reasons,
        )

    def annotate_signal(
        self,
        signal: StrategySignal,
        *,
        candles: list[dict[str, Any]] | pd.DataFrame,
        capital: float,
        risk_pct: float,
        h4_candles: list[dict[str, Any]] | pd.DataFrame | None = None,
        h1_candles: list[dict[str, Any]] | pd.DataFrame | None = None,
        m15_candles: list[dict[str, Any]] | pd.DataFrame | None = None,
    ) -> StrategySignal:
        qualification = self.qualify(
            signal,
            candles=candles,
            capital=capital,
            risk_pct=risk_pct,
            h4_candles=h4_candles,
            h1_candles=h1_candles,
            m15_candles=m15_candles,
        )
        signal.metadata["trade_qualification"] = qualification.to_dict()
        signal.metadata["tqe_score"] = qualification.score
        signal.metadata["quality_grade"] = qualification.quality_grade
        signal.metadata["market_context"] = qualification.market_context
        signal.metadata["volume_status"] = qualification.volume_status
        signal.metadata["volatility_status"] = qualification.volatility_status
        signal.metadata["position_size"] = qualification.position_sizing.position_size
        signal.metadata["risk_amount"] = qualification.position_sizing.risk_amount
        signal.metadata["risk_reward"] = qualification.rr
        return signal

    def _empty(self, signal: StrategySignal, capital: float, risk_pct: float, reason: str) -> TradeQualification:
        sizing = self._position_size(signal, capital, risk_pct)
        return TradeQualification(False, reason, 0, self.MAX_SCORE, "Reject", "RANGE", "UNKNOWN", False, {}, "Unknown", "LOW", 0.0, sizing, {}, {}, [reason])

    def _prepare(self, candles: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
        try:
            frame = self.indicators.prepare(candles)
            if not frame.empty and "avg_volume_20" not in frame:
                frame = frame.copy()
                frame["avg_volume_20"] = frame["volume"].fillna(0.0).rolling(20, min_periods=3).mean()
            return frame
        except Exception:
            return pd.DataFrame()

    def _prepare_optional(self, candles: Any) -> pd.DataFrame | None:
        if candles is None:
            return None
        frame = self._prepare(candles)
        return frame if not frame.empty else None

    @staticmethod
    def _row_for_signal(frame: pd.DataFrame, signal: StrategySignal) -> pd.Series:
        matches = frame[frame["timestamp"] <= pd.Timestamp(signal.signal_time)]
        return matches.iloc[-1] if not matches.empty else frame.iloc[-1]

    def _market_context(self, frame: pd.DataFrame) -> MarketContext:
        recent = frame.tail(12)
        if len(recent) < 6:
            return "RANGE"
        highs = recent["high"].astype(float)
        lows = recent["low"].astype(float)
        hh_hl = highs.iloc[-1] > highs.iloc[0] and lows.iloc[-1] > lows.iloc[0]
        lh_ll = highs.iloc[-1] < highs.iloc[0] and lows.iloc[-1] < lows.iloc[0]
        structure_range = float(highs.max() - lows.min())
        atr = float(recent["atr_14"].iloc[-1] or 0.0)
        if structure_range > 0 and atr / structure_range < 0.08:
            return "RANGE"
        if hh_hl:
            return "UPTREND"
        if lh_ll:
            return "DOWNTREND"
        return "RANGE"

    @staticmethod
    def _trend(frame: pd.DataFrame | None) -> str:
        if frame is None or frame.empty:
            return "UNKNOWN"
        row = frame.iloc[-1]
        close = float(row["close"])
        ema21 = float(row["ema_21"])
        ema50 = float(row["ema_50"])
        if close > ema21 > ema50:
            return "UPTREND"
        if close < ema21 < ema50:
            return "DOWNTREND"
        return "RANGE"

    @staticmethod
    def _trend_aligned(side: str, trends: dict[str, str]) -> bool:
        desired = "UPTREND" if side.upper() == "BUY" else "DOWNTREND"
        opposite = "DOWNTREND" if desired == "UPTREND" else "UPTREND"
        votes = list(trends.values())
        return desired in votes and votes.count(opposite) == 0

    @staticmethod
    def _support_resistance(frame: pd.DataFrame, row: pd.Series, side: str) -> dict[str, Any]:
        recent = frame.tail(60)
        swing_high = float(recent["high"].max())
        swing_low = float(recent["low"].min())
        close = float(row["close"])
        atr = max(float(row.get("atr_14", 0.0) or 0.0), close * 0.001, 0.01)
        near_demand = abs(close - swing_low) <= atr * 2.5 or close > swing_low
        near_supply = abs(close - swing_high) <= atr * 2.5 or close < swing_high
        aligned = bool(near_demand if side.upper() == "BUY" else near_supply)
        return {
            "aligned": aligned,
            "swing_high": round(swing_high, 4),
            "swing_low": round(swing_low, 4),
            "daily_high": round(swing_high, 4),
            "daily_low": round(swing_low, 4),
            "weekly_high": round(swing_high, 4),
            "weekly_low": round(swing_low, 4),
            "supply_zone": [round(swing_high - atr, 4), round(swing_high, 4)],
            "demand_zone": [round(swing_low, 4), round(swing_low + atr, 4)],
        }

    @staticmethod
    def _volume_score(row: pd.Series, signal: StrategySignal) -> tuple[int, str]:
        volume = float(row.get("volume", 0.0) or 0.0)
        average = float(row.get("volume", 0.0) or 0.0)
        if "avg_volume_20" in row and pd.notna(row.get("avg_volume_20")):
            average = float(row.get("avg_volume_20") or average)
        relative = volume / average if average > 0 else 1.0
        is_reversal = any(str(signal.metadata.get(key, "")).lower().find(marker) >= 0 for key in ("setup_type", "trap_type", "reason") for marker in ("reversal", "trap", "sweep"))
        if is_reversal and relative >= 1.3:
            return 2, "Volume Confirmed"
        if is_reversal and relative < 0.8:
            return -2, "Low Volume Reversal"
        if relative >= 1.1:
            return 1, "Volume Supported"
        return 0, "Volume Neutral"

    @staticmethod
    def _volatility_score(row: pd.Series) -> tuple[int, VolatilityRegime, bool]:
        close = max(float(row["close"]), 0.01)
        atr_pct = float(row.get("atr_14", 0.0) or 0.0) / close
        if atr_pct < 0.00035:
            return 0, "LOW", True
        if atr_pct > 0.006:
            return 0, "HIGH", True
        return 1, "NORMAL", False

    @staticmethod
    def _indicator_score(row: pd.Series, side: str) -> tuple[int, list[str]]:
        score = 0
        notes: list[str] = []
        close = float(row["close"])
        rsi = float(row.get("rsi", 50.0) or 50.0)
        macd = float(row.get("macd", 0.0) or 0.0)
        macd_signal = float(row.get("macd_signal", 0.0) or 0.0)
        recent_std = float(row.get("atr_14", 0.0) or 0.0)
        boll_mid = float(row.get("ema_21", close) or close)
        boll_upper = boll_mid + recent_std * 2
        boll_lower = boll_mid - recent_std * 2
        if side.upper() == "BUY":
            if rsi >= 45:
                score += 1
                notes.append("RSI agreement")
            if macd >= macd_signal:
                score += 1
                notes.append("MACD agreement")
            if close >= boll_lower:
                score += 1
                notes.append("Bollinger rejection")
        else:
            if rsi <= 55:
                score += 1
                notes.append("RSI agreement")
            if macd <= macd_signal:
                score += 1
                notes.append("MACD agreement")
            if close <= boll_upper:
                score += 1
                notes.append("Bollinger rejection")
        return min(score, 3), notes

    @staticmethod
    def _risk_reward(signal: StrategySignal) -> float:
        risk = abs(float(signal.entry_price) - float(signal.stop_loss))
        reward = abs(float(signal.target_price) - float(signal.entry_price))
        return reward / risk if risk > 0 else 0.0

    @staticmethod
    def _position_size(signal: StrategySignal, capital: float, risk_pct: float) -> PositionSizing:
        risk_fraction = float(risk_pct) / 100.0 if float(risk_pct) >= 1 else float(risk_pct)
        risk_amount = max(0.0, float(capital) * risk_fraction)
        per_unit = abs(float(signal.entry_price) - float(signal.stop_loss))
        size = int(risk_amount // per_unit) if per_unit > 0 else 0
        return PositionSizing(round(float(capital), 2), round(float(risk_pct), 4), round(risk_amount, 2), max(0, size))

    def _execution_checks(self, frame: pd.DataFrame, signal: StrategySignal, execution_mode: str) -> dict[str, Any]:
        candles = frame.tail(100).to_dict("records")
        validation = validate_live_candle(candles, interval="1m", mode=execution_mode)
        latest = normalize_timestamp(candles[-1].get("timestamp")) if candles else None
        signal_time = normalize_timestamp(signal.signal_time)
        age_seconds = None
        if latest is not None and signal_time is not None:
            age_seconds = max(0.0, (latest.astimezone(timezone.utc) - signal_time.astimezone(timezone.utc)).total_seconds())
        status = risk_status()
        return {
            "market_open": bool(validation.market_live) if execution_mode == "live" else bool(validation.valid_for_analysis),
            "feed_fresh": bool(validation.valid_for_execution),
            "signal_fresh": age_seconds is not None and age_seconds <= 300,
            "risk_limit_available": int(status["open_positions"]) < int(status["max_open_positions"]),
            "daily_loss_available": abs(min(0.0, float(status["daily_pnl"]))) < float(status["max_daily_loss"]),
            "consecutive_losses_ok": int(status["consecutive_losses"]) < int(status["max_consecutive_losses"]),
        }

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 11:
            return "A+"
        if score >= 9:
            return "A"
        if score >= 7:
            return "B"
        if score >= 5:
            return "Watchlist"
        return "Reject"
