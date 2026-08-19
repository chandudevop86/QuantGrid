from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from Backend.application.notifications import send_alert
from Backend.application.risk_engine import RiskEngine, RiskValidationResult
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal
from Backend.domain.shared import IBrokerAdapter


logger = logging.getLogger(__name__)


TERMINAL_BROKER_STATUSES = {
    "filled",
    "cancelled",
    "canceled",
    "rejected",
    "failed",
    "not_found",
}

PARTIAL_BROKER_STATUSES = {
    "partially_filled",
    "partial",
    "part_filled",
}


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
    """
    Order Management Service.

    IMPORTANT:
    OMS does NOT create or update database orders.

    Order persistence is owned by the execution lifecycle layer.
    OMS is responsible for:
      - duplicate protection
      - risk validation
      - broker submission
      - retry/reconciliation
      - returning OMSResult
    """

    def __init__(
        self,
        broker: IBrokerAdapter,
        *,
        risk_engine: RiskEngine | None = None,
        max_retries: int = 1,
    ) -> None:
        self.broker = broker

        # Kept as an optional constructor argument for backwards
        # compatibility with existing callers/tests.
        #
        # OMS no longer uses the repository for persistence.
        

        self.risk_engine = risk_engine or RiskEngine()
        self.max_retries = max(0, int(max_retries))

        self._active_order_keys: set[str] = set()

    async def submit_signal(
        self,
        signal: StrategySignal,
        context: dict[str, Any] | None = None,
    ) -> OMSResult:
        return await self.submit_order(
            self._order_from_signal(signal),
            signal,
            context,
        )

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

        existing_active_order_keys = set(
            self._active_order_keys
        )

        # ---------------------------------------------------------
        # Duplicate protection
        # ---------------------------------------------------------

        if order_key in self._active_order_keys:

            reasons = [
                (
                    f"Duplicate order suppressed: "
                    f"'{order_key}' already has an active order."
                )
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

        try:
            # -----------------------------------------------------
            # Risk
            # -----------------------------------------------------

            risk = context.get("prevalidated_risk")

            if isinstance(risk, dict):
                risk = RiskValidationResult(
                    allowed=bool(
                        risk.get("allowed")
                    ),
                    reasons=list(
                        risk.get("reasons")
                        or (
                            [risk.get("reason")]
                            if risk.get("reason")
                            else ["OK"]
                        )
                    ),
                    risk_score=int(
                        risk.get("risk_score") or 100
                    ),
                    blocked_by=list(
                        risk.get("blocked_by") or []
                    ),
                    warnings=list(
                        risk.get("warnings") or []
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

            # -----------------------------------------------------
            # Risk rejected
            #
            # IMPORTANT:
            # No DB update happens here.
            #
            # The lifecycle layer owns the existing DB order and
            # will transition it to REJECTED.
            # -----------------------------------------------------

            if not risk.allowed:
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

            # -----------------------------------------------------
            # Broker submission
            # -----------------------------------------------------

            return await self._place_with_retry(
                local_order_id=local_order_id,
                order=order,
                risk=risk,
                audit=audit,
            )
        finally:
            final_status = (
                audit[-1]["status"]
                if audit
                else "unknown"
            )

            # Filled / partially-filled orders keep their duplicate key.
            # The lifecycle/position layer must release the key when the
            # resulting position is closed.
            #
            # Rejected/failed/cancelled orders did not establish an active
            # position, so they may be retried.
            if final_status in {
                "rejected",
                "failed",
                "not_found",
                "cancelled",
                "canceled",
            }:
                self._active_order_keys.discard(order_key)
                
    async def _place_with_retry(
        self,
        local_order_id: str,
        order: Order,
        risk: RiskValidationResult,
        audit: list[dict[str, Any]],
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
                    "correlation_id": order.metadata.get(
                        "correlation_id"
                    ),
                },
            )

            try:
                # -------------------------------------------------
                # Broker submission
                # -------------------------------------------------

                broker_result = await self.broker.place_order(
                    order
                )

                status = self._normalize_status(
                    self._value(
                        broker_result,
                        "status",
                    )
                )

                broker_order_id = self._value(
                    broker_result,
                    "broker_order_id",
                )

                average_price = self._value(
                    broker_result,
                    "average_price",
                )

                self._audit(
                    audit,
                    "broker_response",
                    local_order_id,
                    {
                        "status": status,
                        "broker_order_id": broker_order_id,
                        "attempt": attempts,
                        "average_price": average_price,
                    },
                )

                # -------------------------------------------------
                # Notification
                #
                # "Submitted" is NOT "Executed".
                # -------------------------------------------------

                if status == "filled":
                    alert_title = "✅ Trade Executed"

                elif status == "partially_filled":
                    alert_title = "⚠️ Trade Partially Filled"

                elif status == "rejected":
                    alert_title = "❌ Trade Rejected"

                elif status == "failed":
                    alert_title = "❌ Trade Failed"

                else:
                    alert_title = "📤 Order Submitted"

                try:
                    send_alert(
                        alert_title,
                        f"""
Symbol        : {order.symbol}
Side          : {order.side}
Quantity      : {order.quantity}

Broker Order  : {broker_order_id}
Status        : {status}

Average Price : {average_price}

Correlation   : {
    order.metadata.get("correlation_id")
}
""",
                    )
                except Exception:
                    logger.exception(
                        "Failed to send trade notification"
                    )

                # -------------------------------------------------
                # IMPORTANT
                #
                # NO database INSERT.
                # NO database UPDATE.
                #
                # The execution lifecycle owns persistence.
                # -------------------------------------------------

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
                        [
                            f"Broker returned {status}."
                        ],
                        risk.warnings,
                        audit,
                    )

                if status == "partially_filled":
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

                if status == "filled":
                    return self._result(
                        local_order_id,
                        "filled",
                        broker_order_id,
                        risk,
                        attempts,
                        ["Order filled."],
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

                logger.exception(
                    "Broker submission failed for %s",
                    local_order_id,
                )

                # -------------------------------------------------
                # IMPORTANT:
                # Do NOT update DB here.
                #
                # Lifecycle manager will transition the existing
                # order after OMS returns.
                # -------------------------------------------------

                if attempt < self.max_retries:

                    already_placed = (
                        await self._check_already_placed(
                            order
                        )
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
                                "broker_order_id": (
                                    broker_order_id
                                ),
                                "attempt": attempts,
                            },
                        )

                        if status == "partially_filled":
                            return self._result(
                                local_order_id,
                                "partially_filled",
                                broker_order_id,
                                risk,
                                attempts,
                                [
                                    "Order partially filled."
                                ],
                                risk.warnings,
                                audit,
                            )

                        if status == "filled":
                            return self._result(
                                local_order_id,
                                "filled",
                                broker_order_id,
                                risk,
                                attempts,
                                [
                                    "Order filled after "
                                    "broker reconciliation."
                                ],
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
                                [
                                    "OK "
                                    "(recovered after timeout)"
                                ],
                                risk.warnings,
                                audit,
                            )

                    await asyncio.sleep(
                        min(2**attempt, 5)
                    )

        return self._result(
            local_order_id,
            "failed",
            None,
            risk,
            attempts,
            [
                last_error
                or "Broker submission failed."
            ],
            risk.warnings,
            audit,
        )

    async def _check_already_placed(
        self,
        order: Order,
    ) -> Any | None:
        """
        Best-effort lookup for an order the broker may already
        have accepted.

        Used after a broker call raises, for example because of
        a timeout, before retrying.

        This prevents a real duplicate order when the broker
        exposes lookup by correlation ID.
        """

        correlation_id = order.metadata.get(
            "correlation_id"
        )

        lookup = getattr(
            self.broker,
            "find_order_by_correlation_id",
            None,
        )

        if not correlation_id or lookup is None:
            return None

        try:
            return await lookup(correlation_id)
        except Exception:
            logger.exception(
                "Broker reconciliation failed for correlation_id=%s",
                correlation_id,
            )
            return None

    @staticmethod
    def _order_from_signal(
        signal: StrategySignal,
    ) -> Order:

        raw_quantity = signal.metadata.get(
            "quantity"
        )

        # Do NOT use:
        #
        # int(raw_quantity or 1)
        #
        # because quantity=0 must remain zero and be rejected
        # by downstream validation.

        quantity = (
            int(raw_quantity)
            if raw_quantity is not None
            else 1
        )

        return Order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            price=float(signal.entry_price),
            stop_loss=float(signal.stop_loss),
            target_price=float(
                signal.target_price
            ),
            trailing_stop_loss=(
                signal.trailing_stop_loss
            ),
            trailing_stop_pct=(
                signal.trailing_stop_pct
            ),
            created_at=signal.signal_time,
            metadata={
                "strategy": signal.strategy_name,
                **signal.metadata,
            },
        )

    @staticmethod
    def _order_key(
        signal: StrategySignal,
    ) -> str:
        return (
            f"{signal.symbol.upper()}:"
            f"{signal.side.upper()}:"
            f"{signal.strategy_name.upper()}"
        )

    @staticmethod
    def _normalize_status(
        status: Any,
    ) -> str:

        value = (
            str(status or "")
            .strip()
            .lower()
            .replace(" ", "_")
        )

        if value in {
            "confirmed",
            "accepted",
            "open",
            "pending",
        }:
            return "submitted"

        if value in PARTIAL_BROKER_STATUSES:
            return "partially_filled"

        if value in {
            "complete",
            "completed",
            "traded",
        }:
            return "filled"

        return value or "unknown"

    @staticmethod
    def _value(
        payload: Any,
        key: str,
    ) -> Any:

        if isinstance(payload, dict):
            return payload.get(key)

        return getattr(
            payload,
            key,
            None,
        )

    @staticmethod
    def _audit(
        audit: list[dict[str, Any]],
        event: str,
        local_order_id: str,
        details: dict[str, Any],
    ) -> None:

        audit.append(
            {
                "event": event,
                "local_order_id": local_order_id,
                "status": str(
                    details.get("status")
                    or event
                ),
                "details": details,
                "timestamp": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
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
            accepted=status
            in {
                "submitted",
                "filled",
                "partially_filled",
            },
            local_order_id=local_order_id,
            status=status,
            broker_order_id=broker_order_id,
            risk=risk.to_dict(),
            attempts=attempts,
            reasons=reasons,
            warnings=warnings,
            audit_trail=audit,
        )