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
from Backend.infrastructure.repositories.order_repository import OrderRepository
from Backend.domain.order_models import OrderEntity

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
    order_repository: OrderRepository,
    risk_engine: RiskEngine | None = None,
    max_retries: int = 1,
) -> None:
        self.broker = broker
        self.order_repository = order_repository
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

        local_order_id = str(
            context.get("local_order_id")
            or f"OMS-{uuid4().hex[:12]}"
        )

        audit: list[dict[str, Any]] = []

        order_key = self._order_key(signal)

        existing_active_order_keys = set(self._active_order_keys)

        # ------------------------------
        # Duplicate protection
        # ------------------------------

        if order_key in self._active_order_keys:

            reasons = [
                f"Duplicate order suppressed: '{order_key}' already has an active order."
            ]

            risk = RiskValidationResult(
                allowed=False,
                reasons=reasons,
                risk_score=0,
                blocked_by=["DUPLICATE_TRADE"],
                warnings=[],
            )

            self._audit(
                audit,
                "duplicate_suppressed",
                local_order_id,
                {
                    "status": "rejected",
                    "order_key": order_key,
                },
            )

            return self._result(
                local_order_id,
                "rejected",
                None,
                risk,
                0,
                reasons,
                [],
                audit,
            )

        self._active_order_keys.add(order_key)

        db_order = None

        try:

            # ---------------------------------
            # Save NEW order in database
            # ---------------------------------

            # ---------------------------------
# Save NEW order in database
# ---------------------------------

            db = context.get("db_session")
            db_order = None

            if db is not None:

                db_order = OrderEntity(
                    client_order_id=local_order_id,
                    broker_order_id=None,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    filled_quantity=0,
                    remaining_quantity=order.quantity,
                    order_type=order.order_type,
                    price=order.price,
                    average_price=None,
                    stop_loss=order.stop_loss,
                    target_price=order.target_price,
                    trailing_stop_loss=order.trailing_stop_loss,
                    trailing_stop_pct=order.trailing_stop_pct,
                    strategy=signal.strategy_name,
                    exchange=order.metadata.get("exchange"),
                    status="NEW",
                    rejection_reason=None,
                )

                self.order_repository.create(
                    db,
                    db_order,
                )
            risk = context.get("prevalidated_risk")

            if isinstance(risk, dict):

                risk = RiskValidationResult(
                    allowed=bool(risk.get("allowed")),
                    reasons=list(
                        risk.get("reasons")
                        or (
                            [risk.get("reason")]
                            if risk.get("reason")
                            else ["OK"]
                        )
                    ),
                    risk_score=int(
                        risk.get("risk_score")
                        or 100
                    ),
                    blocked_by=list(
                        risk.get("blocked_by")
                        or []
                    ),
                    warnings=list(
                        risk.get("warnings")
                        or []
                    ),
                )

            if risk is None:

                risk = self.risk_engine.validate(
                    signal,
                    {
                        **context,
                        "active_trade_keys": [
                            *context.get(
                                "active_trade_keys",
                                [],
                            ),
                            *existing_active_order_keys,
                        ],
                    },
                )

            self._audit(
                audit,
                "risk_checked",
                local_order_id,
                {
                    "allowed": risk.allowed,
                    "blocked_by": risk.blocked_by,
                },
            )

            # -----------------------------
            # Risk failed
            # -----------------------------

            if not risk.allowed:

                if db_order:

                    db_order.status = "REJECTED"

                    self.order_repository.update(
                        db,
                        db_order,
                    )

                return self._result(
                    local_order_id,
                    "rejected",
                    None,
                    risk,
                    0,
                    risk.reasons,
                    risk.warnings,
                    audit,
                )

            # ------------------------------------
            # Continue to broker
            # ------------------------------------

            return await self._place_with_retry(
                local_order_id=local_order_id,
                order=order,
                risk=risk,
                audit=audit,
                db=db,
                db_order=db_order,
            )

        finally:

            final_status = (
                audit[-1]["status"]
                if audit
                else "unknown"
            )

            if (
                final_status in TERMINAL_BROKER_STATUSES
                or final_status == "rejected"
            ):
                self._active_order_keys.discard(order_key)

    async def _place_with_retry(
    self,
    local_order_id: str,
    order: Order,
    risk: RiskValidationResult,
    audit: list[dict[str, Any]],
    db=None,
    db_order=None,
    ) -> OMSResult:

        order.metadata.setdefault(
            "correlation_id",
            f"OMS-{local_order_id}",
        )

        attempts = 0
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):

            attempts = attempt + 1

            self._audit(
                audit,
                "broker_submit_attempt",
                local_order_id,
                {
                    "attempt": attempts,
                    "correlation_id": order.metadata.get("correlation_id"),
                },
            )

            try:

                broker_result = await self.broker.place_order(order)

                status = self._normalize_status(
                    self._value(broker_result, "status")
                )

                broker_order_id = self._value(
                    broker_result,
                    "broker_order_id",
                )

                self._audit(
                    audit,
                    "broker_response",
                    local_order_id,
                    {
                        "status": status,
                        "broker_order_id": broker_order_id,
                        "attempt": attempts,
                    },
                )

                # ---------------------------------------
                # Update database
                # ---------------------------------------

                if db is not None and db_order is not None:

                    db_order.broker_order_id = broker_order_id
                    db_order.status = status.upper()

                    filled_qty = self._value(
                        broker_result,
                        "filled_quantity",
                    )

                    if filled_qty is not None:
                        db_order.filled_quantity = filled_qty
                        db_order.remaining_quantity = (
                            db_order.quantity - filled_qty
                        )

                    avg_price = self._value(
                        broker_result,
                        "average_price",
                    )

                    if avg_price is not None:
                        db_order.average_price = avg_price

                    rejection_reason = self._value(
                        broker_result,
                        "rejection_reason",
                    )

                    if rejection_reason:
                        db_order.rejection_reason = rejection_reason

                    self.order_repository.update(
                        db,
                        db_order,
                    )

                if status in {
                    "rejected",
                    "failed",
                    "not_found",
                }:

                    return self._result(
                        local_order_id,
                        status,
                        broker_order_id,
                        risk,
                        attempts,
                        [f"Broker returned {status}."],
                        risk.warnings,
                        audit,
                    )

                if status in PARTIAL_BROKER_STATUSES:

                    return self._result(
                        local_order_id,
                        "partially_filled",
                        broker_order_id,
                        risk,
                        attempts,
                        ["Order partially filled."],
                        risk.warnings,
                        audit,
                    )

                return self._result(
                    local_order_id,
                    "submitted",
                    broker_order_id,
                    risk,
                    attempts,
                    ["OK"],
                    risk.warnings,
                    audit,
                )

            except Exception as exc:

                last_error = str(exc)

                self._audit(
                    audit,
                    "broker_error",
                    local_order_id,
                    {
                        "attempt": attempts,
                        "error": last_error,
                    },
                )

                # -------------------------
                # Save FAILED status
                # -------------------------

                if db is not None and db_order is not None:

                    db_order.status = "FAILED"
                    db_order.rejection_reason = last_error

                    self.order_repository.update(
                        db,
                        db_order,
                    )

                if attempt < self.max_retries:

                    already_placed = await self._check_already_placed(
                        order
                    )

                    if already_placed is not None:

                        status = self._normalize_status(
                            self._value(
                                already_placed,
                                "status",
                            )
                        )

                        broker_order_id = self._value(
                            already_placed,
                            "broker_order_id",
                        )

                        self._audit(
                            audit,
                            "broker_duplicate_avoided",
                            local_order_id,
                            {
                                "status": status,
                                "broker_order_id": broker_order_id,
                                "attempt": attempts,
                            },
                        )

                        if db is not None and db_order is not None:

                            db_order.status = status.upper()
                            db_order.broker_order_id = broker_order_id

                            self.order_repository.update(
                                db,
                                db_order,
                            )

                        if status in PARTIAL_BROKER_STATUSES:

                            return self._result(
                                local_order_id,
                                "partially_filled",
                                broker_order_id,
                                risk,
                                attempts,
                                ["Order partially filled."],
                                risk.warnings,
                                audit,
                            )

                        if status not in {
                            "rejected",
                            "failed",
                            "not_found",
                        }:

                            return self._result(
                                local_order_id,
                                "submitted",
                                broker_order_id,
                                risk,
                                attempts,
                                ["OK (recovered after timeout)"],
                                risk.warnings,
                                audit,
                            )

                    await asyncio.sleep(
                        min(2 ** attempt, 5)
                    )

        if db is not None and db_order is not None:

            db_order.status = "FAILED"
            db_order.rejection_reason = (
                last_error
                or "Broker submission failed."
            )

            self.order_repository.update(
                db,
                db_order,
            )

        return self._result(
            local_order_id,
            "failed",
            None,
            risk,
            attempts,
            [last_error or "Broker submission failed."],
            risk.warnings,
            audit,
        )
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
