from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from Backend.application.risk_engine import RiskEngine, RiskValidationResult
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal
from Backend.domain.shared import IBrokerAdapter


TERMINAL_BROKER_STATUSES = {"filled", "cancelled", "canceled", "rejected", "failed", "not_found"}
PARTIAL_BROKER_STATUSES = {"partially_filled", "partial", "part_filled"}


@dataclass(frozen=True, slots=True)
class OMSResult:
    accepted: bool
    local_order_id: str
    status: str
    broker_order_id: str | None
    risk: dict[str, Any]
    attempts: int
    reasons: list[str]
    warnings: list[str]
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderManagementService:
    def __init__(
        self,
        broker: IBrokerAdapter,
        *,
        risk_engine: RiskEngine | None = None,
        max_retries: int = 1,
    ) -> None:
        self.broker = broker
        self.risk_engine = risk_engine or RiskEngine()
        self.max_retries = max(0, int(max_retries))
        self._active_order_keys: set[str] = set()

    async def submit_signal(self, signal: StrategySignal, context: dict[str, Any] | None = None) -> OMSResult:
        return await self.submit_order(self._order_from_signal(signal), signal, context)

    async def submit_order(
        self,
        order: Order,
        signal: StrategySignal,
        context: dict[str, Any] | None = None,
    ) -> OMSResult:
        context = dict(context or {})
        local_order_id = str(context.get("local_order_id") or f"OMS-{uuid4().hex[:12]}")
        audit: list[dict[str, Any]] = []
        order_key = self._order_key(signal)
        risk = context.get("prevalidated_risk")
        if isinstance(risk, dict):
            risk = RiskValidationResult(
                allowed=bool(risk.get("allowed")),
                reasons=list(risk.get("reasons") or ([risk.get("reason")] if risk.get("reason") else ["OK"])),
                risk_score=int(risk.get("risk_score") or 100),
                blocked_by=list(risk.get("blocked_by") or []),
                warnings=list(risk.get("warnings") or []),
            )
        if risk is None:
            risk = self.risk_engine.validate(
                signal,
                {
                    **context,
                    "active_trade_keys": [*context.get("active_trade_keys", []), *self._active_order_keys],
                },
            )
        self._audit(audit, "risk_checked", local_order_id, {"allowed": risk.allowed, "blocked_by": risk.blocked_by})
        if not risk.allowed:
            return self._result(local_order_id, "rejected", None, risk, 0, risk.reasons, risk.warnings, audit)

        self._active_order_keys.add(order_key)
        try:
            return await self._place_with_retry(local_order_id, order, risk, audit)
        finally:
            final_status = audit[-1]["status"] if audit else "unknown"
            if final_status in TERMINAL_BROKER_STATUSES or final_status == "rejected":
                self._active_order_keys.discard(order_key)

    async def _place_with_retry(
        self,
        local_order_id: str,
        order: Order,
        risk: RiskValidationResult,
        audit: list[dict[str, Any]],
    ) -> OMSResult:
        attempts = 0
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1
            self._audit(audit, "broker_submit_attempt", local_order_id, {"attempt": attempts})
            try:
                broker_result = await self.broker.place_order(order)
                status = self._normalize_status(self._value(broker_result, "status"))
                broker_order_id = self._value(broker_result, "broker_order_id")
                self._audit(
                    audit,
                    "broker_response",
                    local_order_id,
                    {"status": status, "broker_order_id": broker_order_id, "attempt": attempts},
                )
                if status in {"rejected", "failed", "not_found"}:
                    return self._result(local_order_id, status, broker_order_id, risk, attempts, [f"Broker returned {status}."], risk.warnings, audit)
                if status in PARTIAL_BROKER_STATUSES:
                    return self._result(local_order_id, "partially_filled", broker_order_id, risk, attempts, ["Order partially filled."], risk.warnings, audit)
                return self._result(local_order_id, "submitted", broker_order_id, risk, attempts, ["OK"], risk.warnings, audit)
            except Exception as exc:
                last_error = str(exc)
                self._audit(audit, "broker_error", local_order_id, {"attempt": attempts, "error": last_error})
                if attempt < self.max_retries:
                    await asyncio.sleep(0)

        return self._result(local_order_id, "failed", None, risk, attempts, [last_error or "Broker submission failed."], risk.warnings, audit)

    @staticmethod
    def _order_from_signal(signal: StrategySignal) -> Order:
        return Order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=int(signal.metadata.get("quantity") or 1),
            price=float(signal.entry_price),
            stop_loss=float(signal.stop_loss),
            target_price=float(signal.target_price),
            trailing_stop_loss=signal.trailing_stop_loss,
            trailing_stop_pct=signal.trailing_stop_pct,
            created_at=signal.signal_time,
            metadata={"strategy": signal.strategy_name, **signal.metadata},
        )

    @staticmethod
    def _order_key(signal: StrategySignal) -> str:
        return f"{signal.symbol.upper()}:{signal.side.upper()}:{signal.strategy_name.upper()}"

    @staticmethod
    def _normalize_status(status: Any) -> str:
        value = str(status or "").strip().lower().replace(" ", "_")
        if value in {"confirmed", "accepted", "open", "pending"}:
            return "submitted"
        if value in PARTIAL_BROKER_STATUSES:
            return "partially_filled"
        if value in {"complete", "completed", "traded"}:
            return "filled"
        return value or "unknown"

    @staticmethod
    def _value(payload: Any, key: str) -> Any:
        if isinstance(payload, dict):
            return payload.get(key)
        return getattr(payload, key, None)

    @staticmethod
    def _audit(audit: list[dict[str, Any]], event: str, local_order_id: str, details: dict[str, Any]) -> None:
        audit.append(
            {
                "event": event,
                "local_order_id": local_order_id,
                "status": str(details.get("status") or event),
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @staticmethod
    def _result(
        local_order_id: str,
        status: str,
        broker_order_id: str | None,
        risk: RiskValidationResult,
        attempts: int,
        reasons: list[str],
        warnings: list[str],
        audit: list[dict[str, Any]],
    ) -> OMSResult:
        return OMSResult(
            accepted=status in {"submitted", "filled", "partially_filled"},
            local_order_id=local_order_id,
            status=status,
            broker_order_id=broker_order_id,
            risk=risk.to_dict(),
            attempts=attempts,
            reasons=reasons,
            warnings=warnings,
            audit_trail=audit,
        )
