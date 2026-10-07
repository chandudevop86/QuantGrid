from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Backend.domain.models.order import Order
from Backend.infrastructure.broker.broker_client import BrokerOrderResult
from Backend.infrastructure.broker.dhan_status import dhan_credentials
from Backend.infrastructure.market_data.dhan_sdk import DhanSdkUnavailable, dhan_sdk_client
from Backend.infrastructure.http_safety import require_https_url


DHAN_BASE_URL = "https://api.dhan.co/v2"
INDEX_SYMBOLS = {"NIFTY", "NIFTY50", "NIFTY_50", "BANKNIFTY", "NIFTYBANK", "FINNIFTY", "MIDCPNIFTY"}
INDEX_SPOT_SECURITY_IDS = {"13"}
ALLOWED_EXCHANGE_SEGMENTS = {"NSE_EQ", "NSE_FNO", "BSE_EQ", "BSE_FNO", "MCX_COMM"}
ALLOWED_PRODUCT_TYPES = {"INTRADAY", "CNC", "MARGIN", "MTF", "CO", "BO"}
ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}
ALLOWED_VALIDITIES = {"DAY", "IOC"}


class BrokerAdapterError(RuntimeError):
    pass


class DhanBrokerClient:
    # Dhan exposes partial-fill states through order status/order book. Broker-
    # native protective-stop acknowledgement is not yet implemented by QuantGrid,
    # so the capability must remain false until that lifecycle is proven.
    supports_partial_fills = True
    supports_protected_order_submission = True
    supports_broker_native_protective_stop = False

    def __init__(self, *, timeout: float = 8.0) -> None:
        credentials = dhan_credentials()
        self.client_id = credentials["client_id"]
        self.access_token = credentials["access_token"]
        self.timeout = timeout
        if not self.client_id or not self.access_token:
            raise BrokerAdapterError("broker not configured")

    async def authenticate(self) -> dict[str, Any]:
        return {"authenticated": bool(self.client_id and self.access_token), "provider": "dhan", "live": True}

    async def get_margin(self) -> dict[str, Any]:
        try:
            raw = await asyncio.to_thread(self._request, "GET", "/fundlimit")
        except BrokerAdapterError:
            raw = await asyncio.to_thread(self._request, "GET", "/margincalculator")
        return {"provider": "dhan", "raw": _safe_raw(raw)}

    async def place_order(self, order: Order) -> BrokerOrderResult:
        security_id = str(order.metadata.get("security_id") or os.getenv(f"DHAN_SECURITY_ID_{order.symbol.upper()}", "")).strip()
        payload = {
            "dhanClientId": self.client_id,
            "correlationId": str(order.metadata.get("correlation_id") or ""),
            "transactionType": order.side.upper(),
            "exchangeSegment": str(order.metadata.get("exchange_segment") or os.getenv("DHAN_EXCHANGE_SEGMENT", "NSE_FNO")),
            "productType": str(order.metadata.get("product_type") or os.getenv("DHAN_PRODUCT_TYPE", "INTRADAY")),
            "orderType": str(
                order.metadata.get("order_type")
                or getattr(order.order_type, "value", order.order_type)
                or os.getenv("DHAN_ORDER_TYPE", "MARKET")
            ),
            "validity": str(order.metadata.get("validity") or os.getenv("DHAN_VALIDITY", "DAY")),
            "securityId": security_id,
            "quantity": int(order.quantity),
            "price": float(order.price or 0.0),
            "triggerPrice": 0.0,
            "afterMarketOrder": False,
        }
        _validate_order_payload(order, payload)
        if _sdk_enabled():
            try:
                raw = await asyncio.to_thread(self._sdk_place_order, order, payload)
                order_id = _extract_order_id(raw)
                if not order_id:
                    raise BrokerAdapterError("order rejected: broker did not return order id")
                return _result_from_raw(
                    order_id,
                    raw,
                    fallback_order=order,
                    message="DhanHQ SDK accepted order request.",
                    confirmed=False,
                )
            except DhanSdkUnavailable:
                pass
        raw = await asyncio.to_thread(self._request, "POST", "/orders", payload)
        order_id = _extract_order_id(raw)
        if not order_id:
            raise BrokerAdapterError("order rejected: broker did not return order id")
        return _result_from_raw(
            order_id,
            raw,
            fallback_order=order,
            message="Dhan accepted order request.",
            confirmed=False,
        )

    async def place_protected_order(self, order: Order) -> BrokerOrderResult:
        """Place a Dhan Super Order with broker-managed target and stop-loss legs."""
        security_id = str(order.metadata.get("security_id") or os.getenv(f"DHAN_SECURITY_ID_{order.symbol.upper()}", "")).strip()
        correlation_id = str(order.metadata.get("correlation_id") or "").strip()
        payload = {
            "dhanClientId": self.client_id,
            "correlationId": correlation_id,
            "transactionType": order.side.upper(),
            "exchangeSegment": str(order.metadata.get("exchange_segment") or os.getenv("DHAN_EXCHANGE_SEGMENT", "NSE_FNO")),
            "productType": str(order.metadata.get("product_type") or os.getenv("DHAN_PRODUCT_TYPE", "INTRADAY")),
            "orderType": str(order.metadata.get("order_type") or getattr(order.order_type, "value", order.order_type) or "MARKET"),
            "securityId": security_id,
            "quantity": int(order.quantity),
            "price": float(order.price or 0.0),
            "targetPrice": float(order.target_price or 0.0),
            "stopLossPrice": float(order.stop_loss or 0.0),
            "trailingJump": float(order.metadata.get("trailing_jump") or 0.0),
        }
        _validate_super_order_payload(order, payload)
        raw = await asyncio.to_thread(self._request, "POST", "/super/orders", payload)
        order_id = _extract_order_id(raw)
        if not order_id:
            raise BrokerAdapterError("protected order rejected: broker did not return order id")
        return _result_from_raw(
            order_id,
            raw,
            fallback_order=order,
            message="Dhan accepted broker-native protected Super Order.",
            confirmed=False,
        )

    async def get_super_orders(self) -> list[dict[str, Any]]:
        raw = await asyncio.to_thread(self._request, "GET", "/super/orders")
        data = raw if isinstance(raw, list) else raw.get("data", raw)
        return _safe_raw(data if isinstance(data, list) else [])

    async def get_super_order_status(self, broker_order_id: str) -> BrokerOrderResult | None:
        """Return parent Super Order state plus normalized target/stop leg evidence."""
        normalized = str(broker_order_id or "").strip()
        if not normalized or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", normalized):
            return None
        orders = await self.get_super_orders()
        parent = next(
            (item for item in orders if str(item.get("orderId") or "") == normalized),
            None,
        )
        if not isinstance(parent, dict):
            return None
        result = _result_from_raw(
            normalized,
            parent,
            message="Dhan Super Order state fetched for protective-leg reconciliation.",
        )
        legs = _super_order_leg_state(parent)
        result.metadata["super_order"] = {
            "leg_name": str(parent.get("legName") or ""),
            "legs": legs,
            "protection": _super_order_protection_state(result, legs),
        }
        return result

    async def modify_order(self, broker_order_id: str, updates: dict[str, Any]) -> BrokerOrderResult:
        payload = {
            key: value
            for key, value in {
                "quantity": updates.get("quantity"),
                "price": updates.get("price"),
                "triggerPrice": updates.get("trigger_price"),
                "orderType": updates.get("order_type"),
                "validity": updates.get("validity"),
            }.items()
            if value is not None
        }
        raw = await asyncio.to_thread(self._request, "PUT", f"/orders/{broker_order_id}", payload)
        return _result_from_raw(broker_order_id, raw, message="Dhan modify request completed.")

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        if _sdk_enabled():
            try:
                raw = await asyncio.to_thread(self._sdk_client().cancel_order, broker_order_id)
                return _result_from_raw(broker_order_id, raw, message="DhanHQ SDK cancel request completed.")
            except DhanSdkUnavailable:
                pass
        raw = await asyncio.to_thread(self._request, "DELETE", f"/orders/{broker_order_id}")
        return _result_from_raw(broker_order_id, raw, message="Dhan cancel request completed.")

    async def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        if _sdk_enabled():
            try:
                raw = await asyncio.to_thread(self._sdk_client().get_order_by_id, broker_order_id)
                return _result_from_raw(broker_order_id, raw, message="DhanHQ SDK order status fetched.")
            except DhanSdkUnavailable:
                pass
        raw = await asyncio.to_thread(self._request, "GET", f"/orders/{broker_order_id}")
        return _result_from_raw(broker_order_id, raw, message="Dhan order status fetched.")

    async def get_positions(self) -> list[dict[str, Any]]:
        if _sdk_enabled():
            try:
                raw = await asyncio.to_thread(self._sdk_client().get_positions)
                return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))
            except DhanSdkUnavailable:
                pass
        raw = await asyncio.to_thread(self._request, "GET", "/positions")
        return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))

    async def get_holdings(self) -> list[dict[str, Any]]:
        if _sdk_enabled():
            try:
                raw = await asyncio.to_thread(self._sdk_client().get_holdings)
                return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))
            except DhanSdkUnavailable:
                pass
        raw = await asyncio.to_thread(self._request, "GET", "/holdings")
        return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))

    async def get_order_book(self) -> list[dict[str, Any]]:
        if _sdk_enabled():
            try:
                raw = await asyncio.to_thread(self._sdk_client().get_order_list)
                return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))
            except DhanSdkUnavailable:
                pass
        raw = await asyncio.to_thread(self._request, "GET", "/orders")
        return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))

    async def find_order_by_correlation_id(self, correlation_id: str) -> BrokerOrderResult | None:
        """Authoritatively query Dhan by the client correlation ID after an ambiguous submit.

        A missing result is still not proof that resubmission is safe. The caller must
        keep the durable submission intent locked and require reconciliation.
        """
        normalized = str(correlation_id or "").strip()
        if not normalized:
            return None
        # Dhan correlation IDs are application-generated identifiers. Reject
        # anything outside the broker-safe identifier alphabet instead of
        # interpolating arbitrary input into an outbound request path.
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", normalized):
            return None
        try:
            raw = await asyncio.to_thread(
                self._request,
                "GET",
                f"/orders/external/{normalized}",
            )
        except BrokerAdapterError:
            return None
        order_id = _extract_order_id(raw)
        if not order_id:
            return None
        return _result_from_raw(
            order_id,
            raw,
            message="Dhan order recovered by correlationId after ambiguous submission.",
        )

    def status(self) -> dict[str, Any]:
        return {
            "provider": "dhan",
            "configured": bool(self.client_id and self.access_token),
            "connected": bool(self.client_id and self.access_token),
            "live": True,
        }

    def _sdk_client(self) -> Any:
        return dhan_sdk_client()

    def _sdk_place_order(self, order: Order, payload: dict[str, Any]) -> Any:
        dhan = self._sdk_client()
        return dhan.place_order(
            security_id=str(payload["securityId"]),
            exchange_segment=_sdk_constant(dhan, str(payload["exchangeSegment"])),
            transaction_type=_sdk_constant(dhan, str(payload["transactionType"])),
            quantity=int(payload["quantity"]),
            order_type=_sdk_constant(dhan, str(payload["orderType"])),
            product_type=_sdk_constant(dhan, str(payload["productType"])),
            price=float(payload["price"]),
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        url = require_https_url(f"{DHAN_BASE_URL}{path}", allowed_hosts={"api.dhan.co"})
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "access-token": str(self.access_token),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "QuantGrid/1.0",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # nosec B310
                text = response.read().decode("utf-8")
                return json.loads(text) if text else {}
        except HTTPError as exc:
            raise BrokerAdapterError(_map_http_error(exc)) from exc
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            raise BrokerAdapterError(f"broker request failed: {exc}") from exc


def _extract_order_id(raw: Any) -> str | None:
    if isinstance(raw, list):
        for item in raw:
            order_id = _extract_order_id(item)
            if order_id:
                return order_id
    if isinstance(raw, dict):
        for key in ("orderId", "order_id", "id"):
            value = raw.get(key)
            if value:
                return str(value)
        data = raw.get("data")
        if isinstance(data, dict):
            return _extract_order_id(data)
    return None


def _result_from_raw(
    broker_order_id: str,
    raw: Any,
    *,
    fallback_order: Order | None = None,
    message: str = "",
    confirmed: bool | None = None,
) -> BrokerOrderResult:
    data = _raw_order_payload(raw)
    raw_status = data.get("orderStatus") or data.get("status")
    if not raw_status and isinstance(raw, dict):
        raw_status = raw.get("orderStatus")
    status = _normalize_status(str(raw_status or "pending"))
    quantity = int(data.get("quantity") or (fallback_order.quantity if fallback_order else 0) or 0)
    filled_quantity = int(data.get("filledQty") or data.get("filledQuantity") or 0)
    remaining_raw = data.get("remainingQuantity")
    if remaining_raw is None:
        remaining_quantity = max(0, quantity - filled_quantity)
    else:
        remaining_quantity = max(0, int(remaining_raw))
    # Some broker payloads report partial execution through quantities before
    # their textual status catches up. Preserve that evidence fail-closed.
    if 0 < filled_quantity < quantity:
        status = "partially_filled"
    elif quantity > 0 and filled_quantity >= quantity:
        status = "filled"
    price = data.get("averageTradedPrice") or data.get("price") or (fallback_order.price if fallback_order else None)
    normalized_status = status
    confirmed_status = (
        status in {"pending", "transit", "open", "traded", "filled", "confirmed"}
        if confirmed is None
        else bool(confirmed)
    )
    return BrokerOrderResult(
        broker_order_id=broker_order_id,
        status=normalized_status,
        symbol=str(data.get("tradingSymbol") or data.get("securityId") or (fallback_order.symbol if fallback_order else "")),
        side=str(data.get("transactionType") or (fallback_order.side if fallback_order else "")).upper(),
        quantity=quantity,
        filled_quantity=filled_quantity,
        remaining_quantity=remaining_quantity,
        price=float(price) if price not in {None, ""} else None,
        message=message,
        confirmed=confirmed_status,
        metadata={"raw_safe": _safe_raw(raw)},
    )


def _raw_order_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        first = raw[0] if raw else {}
        return first if isinstance(first, dict) else {}
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data", raw)
    if isinstance(data, list):
        first = data[0] if data else {}
        return first if isinstance(first, dict) else {}
    return data if isinstance(data, dict) else {}


def _normalize_status(value: str) -> str:
    status = value.strip().lower().replace(" ", "_")
    if status in {"traded", "filled", "complete", "completed"}:
        return "filled"
    if status in {"pending", "transit", "open", "after_market_order_req_received"}:
        return "open"
    if status in {"partially_filled", "partial", "part_filled", "part_traded"}:
        return "partially_filled"
    if status in {"rejected", "cancelled", "expired", "failed"}:
        return status
    return status or "pending"


def _validate_order_payload(order: Order, payload: dict[str, Any]) -> None:
    symbol = str(order.symbol or "").upper().strip()
    side = str(payload.get("transactionType") or "").upper()
    security_id = str(payload.get("securityId") or "").strip()
    exchange_segment = str(payload.get("exchangeSegment") or "").upper()
    product_type = str(payload.get("productType") or "").upper()
    order_type = str(payload.get("orderType") or "").upper()
    validity = str(payload.get("validity") or "").upper()
    quantity = int(payload.get("quantity") or 0)
    price = float(payload.get("price") or 0.0)

    if not symbol:
        raise BrokerAdapterError("unsafe order: symbol is required")
    if side not in {"BUY", "SELL"}:
        raise BrokerAdapterError("unsafe order: side must be BUY or SELL")
    if quantity <= 0:
        raise BrokerAdapterError("unsafe order: quantity must be greater than zero")
    if not security_id:
        raise BrokerAdapterError(f"unsafe order: DHAN_SECURITY_ID_{symbol} must be configured")
    if not security_id.isdigit():
        raise BrokerAdapterError("unsafe order: Dhan securityId must be numeric")
    if security_id.upper() == symbol:
        raise BrokerAdapterError("unsafe order: Dhan securityId cannot fall back to the symbol name")
    if symbol in INDEX_SYMBOLS and security_id in INDEX_SPOT_SECURITY_IDS:
        raise BrokerAdapterError("unsafe order: index spot securityId is not tradable; configure a futures/options securityId")
    if exchange_segment not in ALLOWED_EXCHANGE_SEGMENTS:
        raise BrokerAdapterError(f"unsafe order: unsupported Dhan exchange segment {exchange_segment or '-'}")
    if product_type not in ALLOWED_PRODUCT_TYPES:
        raise BrokerAdapterError(f"unsafe order: unsupported Dhan product type {product_type or '-'}")
    if order_type not in ALLOWED_ORDER_TYPES:
        raise BrokerAdapterError(f"unsafe order: unsupported Dhan order type {order_type or '-'}")
    if validity not in ALLOWED_VALIDITIES:
        raise BrokerAdapterError(f"unsafe order: unsupported Dhan validity {validity or '-'}")
    if order_type == "LIMIT" and price <= 0:
        raise BrokerAdapterError("unsafe order: limit orders require a positive price")



def _validate_super_order_payload(order: Order, payload: dict[str, Any]) -> None:
    # Reuse the regular-order validation for symbol, side, instrument, product,
    # quantity and entry order type. Super Orders have DAY validity implicitly.
    regular_payload = {
        **payload,
        "validity": "DAY",
    }
    _validate_order_payload(order, regular_payload)

    correlation_id = str(payload.get("correlationId") or "")
    target = float(payload.get("targetPrice") or 0.0)
    stop = float(payload.get("stopLossPrice") or 0.0)
    trailing_jump = float(payload.get("trailingJump") or 0.0)
    entry = float(order.price or 0.0)

    if not re.fullmatch(r"[A-Za-z0-9 _-]{1,30}", correlation_id):
        raise BrokerAdapterError("unsafe protected order: Dhan correlationId must be 1-30 safe characters")
    if target <= 0 or stop <= 0:
        raise BrokerAdapterError("unsafe protected order: target and stop-loss prices are required")
    if trailing_jump < 0:
        raise BrokerAdapterError("unsafe protected order: trailing jump cannot be negative")
    side = str(order.side or "").upper()
    if entry > 0:
        if side == "BUY" and not (stop < entry < target):
            raise BrokerAdapterError("unsafe protected BUY: require stop_loss < entry < target")
        if side == "SELL" and not (target < entry < stop):
            raise BrokerAdapterError("unsafe protected SELL: require target < entry < stop")


def _super_order_leg_state(parent: dict[str, Any]) -> dict[str, dict[str, Any]]:
    legs: dict[str, dict[str, Any]] = {}
    for raw_leg in parent.get("legDetails") or []:
        if not isinstance(raw_leg, dict):
            continue
        name = str(raw_leg.get("legName") or "").upper()
        if name not in {"TARGET_LEG", "STOP_LOSS_LEG"}:
            continue
        legs[name] = {
            "order_id": str(raw_leg.get("orderId") or ""),
            "status": _normalize_status(str(raw_leg.get("orderStatus") or "pending")),
            "quantity": int(raw_leg.get("totalQuatity") or raw_leg.get("quantity") or 0),
            "remaining_quantity": int(raw_leg.get("remainingQuantity") or 0),
            "triggered_quantity": int(raw_leg.get("triggeredQuantity") or 0),
            "price": float(raw_leg.get("price") or 0.0),
            "trailing_jump": float(raw_leg.get("trailingJump") or 0.0),
        }
    return legs


def _super_order_protection_state(
    parent: BrokerOrderResult,
    legs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stop = legs.get("STOP_LOSS_LEG")
    target = legs.get("TARGET_LEG")
    exposed_quantity = int(parent.filled_quantity or 0)
    stop_status = str((stop or {}).get("status") or "")
    stop_quantity = int((stop or {}).get("triggered_quantity") or (stop or {}).get("quantity") or 0)
    stop_active = bool(
        stop
        and stop_status not in {"rejected", "cancelled", "expired", "failed"}
        and (exposed_quantity == 0 or stop_quantity >= exposed_quantity)
    )
    return {
        "exposed_quantity": exposed_quantity,
        "stop_loss_present": stop is not None,
        "target_present": target is not None,
        "stop_loss_active": stop_active,
        "protected": bool(exposed_quantity == 0 or stop_active),
    }


def _sdk_constant(dhan: Any, value: str) -> Any:
    aliases = {
        "INTRADAY": "INTRA",
        "MARKET": "MARKET",
        "LIMIT": "LIMIT",
        "BUY": "BUY",
        "SELL": "SELL",
        "NSE_FNO": "NSE_FNO",
        "NSE": "NSE",
        "BSE": "BSE",
    }
    attr = aliases.get(value.upper(), value.upper())
    return getattr(dhan, attr, value)


def _sdk_enabled() -> bool:
    return os.getenv("DHAN_USE_SDK", "").strip().lower() in {"1", "true", "yes", "on"}


def _map_http_error(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        payload = {}
    message = str(payload.get("remarks") or payload.get("message") or payload.get("errorMessage") or payload.get("errorType") or exc.reason or "")
    lower = message.lower()
    if exc.code in {401, 403}:
        return "token expired or invalid"
    if "margin" in lower or "fund" in lower:
        return "insufficient margin"
    if "market" in lower and ("closed" in lower or "close" in lower):
        return "market closed"
    if "reject" in lower or exc.code == 400:
        return f"order rejected: {message}"
    return f"broker rejected request: HTTP {exc.code} {message}".strip()


def _safe_raw(value: Any) -> Any:
    secret_keys = {"access-token", "access_token", "accesstoken", "token", "authorization", "clientsecret", "apisecret"}
    normalized_secret_keys = {item.lower() for item in secret_keys}
    if isinstance(value, dict):
        return {key: ("[redacted]" if str(key).lower() in normalized_secret_keys else _safe_raw(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_raw(item) for item in value]
    return value
