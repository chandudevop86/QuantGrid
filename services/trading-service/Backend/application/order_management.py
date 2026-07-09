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
        existing_active_order_keys = set(self._active_order_keys)

        # Reserve the order key BEFORE running risk validation, not after. Reserving it
        # after the check leaves a window where two concurrent submissions for the same
        # symbol/side/strategy can both pass validation before either registers itself,
        # defeating the duplicate-order guard entirely (classic check-then-act race).
        if order_key in self._active_order_keys:
            reasons = [f"Duplicate order suppressed: '{order_key}' already has an active order in flight."]
            risk = RiskValidationResult(allowed=False, reasons=reasons, risk_score=0, blocked_by=["DUPLICATE_TRADE"], warnings=[])
            self._audit(audit, "duplicate_suppressed", local_order_id, {"status": "rejected", "order_key": order_key})
            return self._result(local_order_id, "rejected", None, risk, 0, reasons, [], audit)
        self._active_order_keys.add(order_key)

        try:
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
                        "active_trade_keys": [*context.get("active_trade_keys", []), *existing_active_order_keys],
                    },
                )
            self._audit(audit, "risk_checked", local_order_id, {"allowed": risk.allowed, "blocked_by": risk.blocked_by})
            if not risk.allowed:
                return self._result(local_order_id, "rejected", None, risk, 0, risk.reasons, risk.warnings, audit)

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
        # Stamp a single correlation/idempotency id on the order once, before the first
        # attempt, and reuse the SAME order object (and therefore the same id) across every
        # retry. If a broker call times out after the order was actually accepted (the
        # response just never came back), a broker/adapter that supports correlation ids can
        # recognize the retry as the same logical order instead of creating a second, real,
        # duplicate order. Without this, every retry after a timeout is indistinguishable
        # from a brand-new order request.
        order.metadata.setdefault("correlation_id", f"OMS-{local_order_id}")

        attempts = 0
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1
            self._audit(audit, "broker_submit_attempt", local_order_id, {"attempt": attempts, "correlation_id": order.metadata.get("correlation_id")})
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
                    # A network/timeout error is precisely the ambiguous case where the
                    # order may have already been accepted broker-side. Before firing a
                    # second live order, ask the broker whether it already knows about this
                    # correlation id / has an order for this key. If the adapter can't answer
                    # that (no support for it), fall back to the previous behavior but at
                    # least back off instead of retrying instantly into a possible outage.
                    already_placed = await self._check_already_placed(order)
                    if already_placed is not None:
                        status = self._normalize_status(self._value(already_placed, "status"))
                        broker_order_id = self._value(already_placed, "broker_order_id")
                        self._audit(
                            audit,
                            "broker_duplicate_avoided",
                            local_order_id,
                            {"status": status, "broker_order_id": broker_order_id, "attempt": attempts},
                        )
                        if status in PARTIAL_BROKER_STATUSES:
                            return self._result(local_order_id, "partially_filled", broker_order_id, risk, attempts, ["Order partially filled."], risk.warnings, audit)
                        if status not in {"rejected", "failed", "not_found"}:
                            return self._result(local_order_id, "submitted", broker_order_id, risk, attempts, ["OK (recovered after timeout)"], risk.warnings, audit)
                    await asyncio.sleep(min(2 ** attempt, 5))

        return self._result(local_order_id, "failed", None, risk, attempts, [last_error or "Broker submission failed."], risk.warnings, audit)

    async def _check_already_placed(self, order: Order) -> Any | None:
        """Best-effort lookup for an order the broker may already have accepted.

        Only used after a broker call raised (e.g. a timeout) and before retrying, to avoid
        placing a real duplicate order. Adapters that don't implement order-book lookup by
        correlation id simply return None here, in which case the caller falls back to a
        plain (backed-off) retry -- this is a mitigation, not a full guarantee, since it
        depends on the broker exposing correlation ids in its order book.
        """
        correlation_id = order.metadata.get("correlation_id")
        lookup = getattr(self.broker, "find_order_by_correlation_id", None)
        if not correlation_id or lookup is None:
            return None
        try:
            return await lookup(correlation_id)
        except Exception:
            return None

    @staticmethod
    def _order_from_signal(signal: StrategySignal) -> Order:
        raw_quantity = signal.metadata.get("quantity")
        # NOTE: this used to be `int(signal.metadata.get("quantity") or 1)`, which silently
        # turns an intentionally-computed quantity of 0 (e.g. risk sizing decided the
        # position should not be taken) into a real order for 1 lot, because `0 or 1`
        # evaluates to `1` in Python. Only fall back to a default when quantity is genuinely
        # absent, and let downstream risk validation reject non-positive quantities instead
        # of this constructor quietly upgrading them.
        quantity = int(raw_quantity) if raw_quantity is not None else 1
        return Order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
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
