from .audit import TradeAudit


class TradeAuditBuilder:

    @staticmethod
    def build(signal, trade) -> TradeAudit:

        metadata = trade.metadata or {}

        return TradeAudit(
            trade_id=metadata.get("trade_id", ""),
            strategy=trade.strategy,
            symbol=trade.symbol,

            validation_score=float(metadata.get("signal_score", 0)),

            trend=metadata.get("trend", "UNKNOWN"),

            bos=metadata.get("bos", False),

            choch=metadata.get("choch", False),

            liquidity_sweep=metadata.get("liquidity_sweep", False),

            sweep_quality=float(metadata.get("sweep_quality", 0)),

            fvg=metadata.get("fvg", False),

            supply_zone=metadata.get("supply_zone", False),

            demand_zone=metadata.get("demand_zone", False),

            risk_reward=trade.rr,

            exit_reason=metadata.get("exit_reason", ""),

            reasons=list(metadata.get("reasons", [])),
        )