from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder
from Backend.domain.supply_demand.entry import EntryConfirmationEngine
from Backend.domain.supply_demand.htf import HTFAnalyzer
from Backend.domain.supply_demand.liquidity import SDLiquidityDetector
from Backend.domain.supply_demand.models import EntryConfirmation, HTFBias, LiquidityEvent, SDZone, Side
from Backend.domain.supply_demand.risk import SDRiskManager
from Backend.domain.supply_demand.scoring import SDScoringEngine
from Backend.domain.supply_demand.zones import ZoneDetectionEngine


@dataclass(slots=True)
class SupplyDemandConfig(StrategyConfig):
    zone_lookback: int = 90
    max_base_candles: int = 5
    max_zone_touches: int = 1
    min_atr_pct: float = 0.0007
    min_score: int = 6
    max_trades_per_day: int = 2
    min_rr: float = 2.0
    require_htf_alignment: bool = True
    require_entry_confirmation: bool = True
    require_vwap_filter: bool = True
    prefer_liquidity_sweep: bool = True

    @classmethod
    def for_mode(cls, mode: str) -> "SupplyDemandConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, max_zone_touches=0, min_score=7, min_atr_pct=0.001, require_htf_alignment=True)
        if normalized == "Aggressive":
            return replace(base, max_zone_touches=1, min_score=6, min_atr_pct=0.0005, require_htf_alignment=False)
        return base


class SupplyDemandStrategy(BaseStrategy):
    name = "Supply Demand"

    def __init__(self, config: SupplyDemandConfig | None = None) -> None:
        super().__init__(config or SupplyDemandConfig())
        self.config: SupplyDemandConfig
        self.zone_engine = ZoneDetectionEngine(
            lookback=self.config.zone_lookback,
            max_base_candles=self.config.max_base_candles,
            max_touches=self.config.max_zone_touches,
        )
        self.htf = HTFAnalyzer()
        self.liquidity = SDLiquidityDetector()
        self.entry = EntryConfirmationEngine()
        self.scoring = SDScoringEngine()
        self.risk = SDRiskManager(self.zone_engine)
        self.signal_builder = SignalBuilder()

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        htf_candles = self.htf.prepare(context.params.get("htf_candles") or context.params.get("higher_timeframe"))
        signals: list[StrategySignal] = []
        trade_count_by_session: dict[str, int] = {}
        start_index = max(20, self.config.max_base_candles + 5)

        for index in range(start_index, len(candles)):
            row = candles.iloc[index]
            session = str(row["session_day"])
            if trade_count_by_session.get(session, 0) >= int(self.config.max_trades_per_day):
                continue
            if self._low_volatility(row):
                continue

            for side in ("BUY", "SELL"):
                signal = self._evaluate_side(candles, index, side=side, context=context, htf_candles=htf_candles)
                if signal is None:
                    continue
                signals.append(signal)
                trade_count_by_session[session] = trade_count_by_session.get(session, 0) + 1
                break

        return signals

    def _evaluate_side(
        self,
        candles: pd.DataFrame,
        index: int,
        *,
        side: Side,
        context: StrategyContext,
        htf_candles: pd.DataFrame | None,
    ) -> StrategySignal | None:
        row = candles.iloc[index]
        htf_bias = self.htf.aligns(htf_candles, row, side)
        if self.config.require_htf_alignment and not htf_bias.aligns(side):
            return None
        if self.config.require_vwap_filter and not self._passes_vwap_filter(candles, index, side):
            return None

        for zone in self.zone_engine.zones_for_return(candles, index, side):
            entry_confirmation = self.entry.confirm(candles, index, side, zone)
            if self.config.require_entry_confirmation and entry_confirmation is None:
                continue
            if entry_confirmation is None:
                continue

            liquidity_event = self.liquidity.detect_near_zone(candles, index, side, zone)
            momentum_ok = self.scoring.momentum_confirmed(candles, index, side)
            score = self.scoring.score(
                zone=zone,
                htf_bias=htf_bias,
                entry=entry_confirmation,
                liquidity=liquidity_event,
                momentum_confirmed=momentum_ok,
                side=side,
            )
            if score.total < int(self.config.min_score):
                continue

            stop_loss, target = self.risk.levels(
                candles,
                index,
                side=side,
                zone=zone,
                entry=float(row["close"]),
                min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
            )
            return self.signal_builder.build(
                row,
                strategy_name=self.name,
                symbol=context.symbol,
                side=side,
                capital=context.capital,
                risk_pct=context.risk_pct,
                stop_loss=stop_loss,
                target_price=target,
                score=score.total,
                metadata=self._metadata(zone, htf_bias, entry_confirmation, liquidity_event, score.to_dict()),
            )
        return None

    def _metadata(
        self,
        zone: SDZone,
        htf_bias: HTFBias,
        entry_confirmation: EntryConfirmation,
        liquidity_event: LiquidityEvent | None,
        score_breakdown: dict[str, Any],
    ) -> dict[str, Any]:
        reason_parts = [str(item) for item in score_breakdown["reasons"]]
        return {
            "zone_type": zone.zone_type,
            "zone": [round(zone.low, 4), round(zone.high, 4)],
            "zone_touches": zone.touches,
            "impulse_strength": round(zone.impulse_strength, 2),
            "htf_bias": htf_bias.bias,
            "entry_confirmation": entry_confirmation.kind,
            "liquidity_sweep": liquidity_event.reason if liquidity_event else None,
            "score_breakdown": score_breakdown,
            "reason": "; ".join(reason_parts),
            "market_signal": f"{zone.zone_type} return + {entry_confirmation.kind} confirmation",
        }

    def _passes_vwap_filter(self, candles: pd.DataFrame, index: int, side: Side) -> bool:
        row = candles.iloc[index]
        previous = candles.iloc[index - 1] if index > 0 else row
        close = float(row["close"])
        vwap = float(row["vwap"])
        if side == "BUY":
            above_vwap = close >= vwap
            reclaim = float(previous["close"]) < float(previous["vwap"]) and close >= vwap
            return above_vwap or reclaim
        below_vwap = close <= vwap
        reject = float(previous["close"]) > float(previous["vwap"]) and close <= vwap
        return below_vwap or reject

    def _low_volatility(self, row: pd.Series) -> bool:
        close = max(float(row["close"]), 0.01)
        atr_pct = float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0) / close
        return atr_pct < float(self.config.min_atr_pct)

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        typed_side: Side = "BUY" if side.upper() == "BUY" else "SELL"
        zones = self.zone_engine.zones_for_return(candles, index, typed_side)
        if not zones:
            row = candles.iloc[index]
            close = float(row["close"])
            atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.05)
            if typed_side == "BUY":
                return close - atr, close + atr * max(2.0, float(context.rr_ratio))
            return close + atr, close - atr * max(2.0, float(context.rr_ratio))
        return self.risk.levels(
            candles,
            index,
            side=typed_side,
            zone=zones[0],
            entry=float(candles.iloc[index]["close"]),
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
        )


def run_supply_demand_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: SupplyDemandConfig | None = None,
) -> list[StrategySignal]:
    return SupplyDemandStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
