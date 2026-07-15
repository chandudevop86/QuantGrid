from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from Backend.application.signal_quality import split_signals
from Backend.application.signal_audit import (
    StrategyAuditInput,
    audit_strategy,
)
from Backend.application.risk_gate import validate_order_risk
from Backend.application.candle_validation import validate_live_candle
from Backend.domain.models.signal import StrategySignal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StrategyRegistration:
    key: str
    label: str
    instance: Any


class TradingCore:

    def __init__(
        self,
        *,
        strategies: list[StrategyRegistration],
        websocket=None,
        paper_trader=None,
        broker=None,
    ):

        self.strategies = strategies
        self.websocket = websocket
        self.paper_trader = paper_trader
        self.broker = broker

    def run(
        self,
        *,
        symbol: str,
        candles_1m: list[dict],
        candles_15m: list[dict] | None = None,
        execution_mode: str = "paper",
    ) -> dict:

        logger.info("Starting TradingCore for %s", symbol)

        candle_validation = validate_live_candle(
            candles_1m,
            mode=execution_mode,
        )

        all_signals: list[StrategySignal] = []

        audit_results = []

        for strategy in self.strategies:

            logger.info("Running %s", strategy.label)

            raw_signals = strategy.instance.generate(
                symbol=symbol,
                candles=candles_1m,
            )

            validated, rejected, stale = split_signals(
                raw_signals,
                candles_1m=candles_1m,
                candles_15m=candles_15m,
            )

            accepted = []

            for signal in validated:

                risk = validate_order_risk(
                    signal,
                    execution_mode=execution_mode,
                    candles_1m=candles_1m,
                )

                if risk.allowed:
                    accepted.append(signal)

            audit_results.append(
                audit_strategy(
                    StrategyAuditInput(
                        key=strategy.key,
                        label=strategy.label,
                        raw_signals=raw_signals,
                        validated_signals=accepted,
                        candles=candles_1m,
                        trend_candles=candles_15m or [],
                        candle_source="LIVE",
                        candle_validation=candle_validation,
                        execution_mode=execution_mode,
                    )
                )
            )

            all_signals.extend(accepted)

        all_signals = self.merge_duplicate_signals(all_signals)

        all_signals = self.rank_signals(all_signals)

        self.publish(all_signals)

        return {
            "signals": all_signals,
            "audit": audit_results,
        }

    def merge_duplicate_signals(
        self,
        signals: list[StrategySignal],
    ) -> list[StrategySignal]:

        merged = {}

        for signal in signals:

            key = (
                signal.symbol,
                signal.side,
            )

            existing = merged.get(key)

            if existing is None:

                merged[key] = signal

                continue

            current = signal.metadata.get("score", 0)
            previous = existing.metadata.get("score", 0)

            if current > previous:

                merged[key] = signal

        return list(merged.values())

    def rank_signals(
        self,
        signals: list[StrategySignal],
    ) -> list[StrategySignal]:

        return sorted(
            signals,
            key=lambda s: (
                s.metadata.get("score", 0),
                s.metadata.get("risk_reward", 0),
            ),
            reverse=True,
        )

    def publish(
        self,
        signals: list[StrategySignal],
    ) -> None:

        if self.paper_trader:

            for signal in signals:

                self.paper_trader.execute(signal)

        if self.broker:

            for signal in signals:

                self.broker.execute(signal)

        if self.websocket:

            self.websocket.publish(
                [signal.to_dict() for signal in signals]
            )

        logger.info(
            "TradingCore published %d signals",
            len(signals),
        )