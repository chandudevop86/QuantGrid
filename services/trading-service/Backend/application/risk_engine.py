from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from Backend.domain.models.signal import StrategySignal


@dataclass(frozen=True, slots=True)
class RiskValidationResult:
    allowed: bool
    reasons: list[str]
    risk_score: int
    blocked_by: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_trades_per_day: int = 3
    max_daily_loss: float = 3000.0
    max_capital_per_trade: float = 25000.0
    max_open_positions: int = 3
    stale_market_data_seconds: int = 120
    high_vix: float = 22.0
    volatility_warning_vix: float = 18.0
    min_risk_reward: float = 1.5
    block_low_liquidity: bool = True


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def validate(self, signal: StrategySignal, context: dict[str, Any]) -> RiskValidationResult:
        reasons: list[str] = []
        blocked_by: list[str] = []
        warnings: list[str] = []

        self._block_if(context.get("kill_switch_active"), "KILL_SWITCH", "Kill switch is active.", reasons, blocked_by)
        self._block_if(int(context.get("trades_today", 0)) >= self.limits.max_trades_per_day, "MAX_TRADES_PER_DAY", "Max trades per day reached.", reasons, blocked_by)
        self._block_if(abs(min(0.0, float(context.get("daily_pnl", 0.0)))) >= self.limits.max_daily_loss, "MAX_DAILY_LOSS", "Max daily loss reached.", reasons, blocked_by)
        self._block_if(float(context.get("capital_per_trade", 0.0)) > self.limits.max_capital_per_trade, "MAX_CAPITAL_PER_TRADE", "Capital per trade is too high.", reasons, blocked_by)
        self._block_if(int(context.get("open_positions", 0)) >= self.limits.max_open_positions, "MAX_OPEN_POSITIONS", "Max open positions reached.", reasons, blocked_by)
        self._block_if(float(signal.stop_loss or 0) <= 0, "STOP_LOSS_REQUIRED", "Stop loss is required.", reasons, blocked_by)
        self._block_if(float(signal.target_price or 0) <= 0, "TARGET_REQUIRED", "Target is required.", reasons, blocked_by)
        self._block_if(float(context.get("market_data_age_seconds", 0)) > self.limits.stale_market_data_seconds, "STALE_MARKET_DATA", "Market data is stale.", reasons, blocked_by)
        self._block_if(float(context.get("vix", 0.0)) >= self.limits.high_vix, "HIGH_VOLATILITY", "Volatility is elevated.", reasons, blocked_by)
        self._block_if(self.limits.block_low_liquidity and self._is_low_liquidity(context), "LOW_LIQUIDITY", "Liquidity is too thin for a reliable options entry.", reasons, blocked_by)
        self._block_if(self._is_duplicate_trade(signal, context), "DUPLICATE_TRADE", "A similar trade is already active.", reasons, blocked_by)
        self._block_if(self._risk_reward(signal) < self.limits.min_risk_reward, "RISK_REWARD_TOO_LOW", "Risk-reward is below the minimum threshold.", reasons, blocked_by)

        if float(context.get("vix", 0.0)) >= self.limits.volatility_warning_vix:
            warnings.append("Volatility is above comfort zone; reduce size or wait for confirmation.")
        if bool(context.get("expiry_day")):
            warnings.append("Expiry-day option decay risk is elevated.")
        if float(context.get("market_data_age_seconds", 0)) > self.limits.stale_market_data_seconds / 2:
            warnings.append("Market data is aging; confirm freshness before entry.")
        if self._is_low_liquidity(context):
            warnings.append("Option liquidity is thin; spreads and exits can slip.")

        risk_score = max(0, 100 - len(blocked_by) * 15 - len(warnings) * 5)
        return RiskValidationResult(
            allowed=not blocked_by,
            reasons=reasons or ["OK"],
            risk_score=risk_score,
            blocked_by=blocked_by,
            warnings=warnings,
        )

    def validate_account(self, context: dict[str, Any]) -> RiskValidationResult:
        reasons: list[str] = []
        blocked_by: list[str] = []
        warnings: list[str] = []

        self._block_if(context.get("kill_switch_active"), "KILL_SWITCH_ACTIVE", "Kill switch is active.", reasons, blocked_by)
        self._block_if(abs(min(0.0, float(context.get("daily_pnl", 0.0)))) >= float(context.get("max_daily_loss", self.limits.max_daily_loss)), "DAILY_LOSS_LIMIT", "Daily loss limit reached.", reasons, blocked_by)
        self._block_if(int(context.get("trades_today", 0)) >= int(context.get("max_trades_per_day", self.limits.max_trades_per_day)), "MAX_TRADES_PER_DAY", "Max trades per day reached.", reasons, blocked_by)
        self._block_if(int(context.get("consecutive_losses", 0)) >= int(context.get("max_consecutive_losses", 10**9)), "MAX_CONSECUTIVE_LOSSES", "Max consecutive losses reached.", reasons, blocked_by)

        if int(context.get("trades_today", 0)) == int(context.get("max_trades_per_day", self.limits.max_trades_per_day)) - 1:
            warnings.append("One trade remains before the daily trade limit.")
        if bool(context.get("expiry_day")):
            warnings.append("Expiry-day risk is elevated.")

        risk_score = max(0, 100 - len(blocked_by) * 20 - len(warnings) * 5)
        return RiskValidationResult(
            allowed=not blocked_by,
            reasons=reasons or ["OK"],
            risk_score=risk_score,
            blocked_by=blocked_by,
            warnings=warnings,
        )

    @staticmethod
    def _block_if(condition: Any, code: str, reason: str, reasons: list[str], blocked_by: list[str]) -> None:
        if bool(condition):
            blocked_by.append(code)
            reasons.append(reason)

    @staticmethod
    def _risk_reward(signal: StrategySignal) -> float:
        if float(signal.stop_loss or 0) <= 0 or float(signal.target_price or 0) <= 0:
            return 0.0
        risk = signal.risk_per_unit
        if risk <= 0:
            return 0.0
        return signal.reward_per_unit / risk

    @staticmethod
    def _is_duplicate_trade(signal: StrategySignal, context: dict[str, Any]) -> bool:
        if bool(context.get("duplicate_trade")):
            return True
        active_keys = {str(item).upper() for item in context.get("active_trade_keys", [])}
        strategy = str(signal.strategy_name).upper()
        symbol = str(signal.symbol).upper()
        side = str(signal.side).upper()
        return f"{symbol}:{side}:{strategy}" in active_keys or f"{symbol}:{side}" in active_keys

    @staticmethod
    def _is_low_liquidity(context: dict[str, Any]) -> bool:
        liquidity = str(
            context.get("liquidity")
            or context.get("liquidity_status")
            or context.get("option_liquidity")
            or ""
        ).strip().upper()
        return liquidity in {"LOW", "THIN", "WEAK", "ILLIQUID"}
