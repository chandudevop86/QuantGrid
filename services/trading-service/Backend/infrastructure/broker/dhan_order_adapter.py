from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Backend.domain.models.order import Order
from Backend.infrastructure.broker.broker_client import BrokerOrderResult
from Backend.infrastructure.broker.dhan_status import dhan_credentials


DHAN_BASE_URL = "https://api.dhan.co/v2"


class BrokerAdapterError(RuntimeError):
    pass


class DhanBrokerClient:
    def __init__(self, *, timeout: float = 8.0) -> None:
        credentials = dhan_credentials()
        self.client_id = credentials["client_id"]
        self.access_token = credentials["access_token"]
        self.timeout = timeout
        if not self.client_id or not self.access_token:
            raise BrokerAdapterError("broker not configured")

    async def place_order(self, order: Order) -> BrokerOrderResult:
        payload = {
            "dhanClientId": self.client_id,
            "correlationId": str(order.metadata.get("correlation_id") or ""),
            "transactionType": order.side.upper(),
            "exchangeSegment": str(order.metadata.get("exchange_segment") or os.getenv("DHAN_EXCHANGE_SEGMENT", "NSE_FNO")),
            "productType": str(order.metadata.get("product_type") or os.getenv("DHAN_PRODUCT_TYPE", "INTRADAY")),
            "orderType": str(order.metadata.get("order_type") or order.order_type or os.getenv("DHAN_ORDER_TYPE", "MARKET")),
            "validity": str(order.metadata.get("validity") or os.getenv("DHAN_VALIDITY", "DAY")),
            "securityId": str(order.metadata.get("security_id") or os.getenv(f"DHAN_SECURITY_ID_{order.symbol.upper()}", order.symbol)),
            "quantity": int(order.quantity),
            "price": float(order.price or 0.0),
            "triggerPrice": 0.0,
            "afterMarketOrder": False,
        }
        raw = await asyncio.to_thread(self._request, "POST", "/orders", payload)
        order_id = _extract_order_id(raw)
        if not order_id:
            raise BrokerAdapterError("order rejected: broker did not return order id")
        return _result_from_raw(order_id, raw, fallback_order=order, message="Dhan accepted order request.")

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        raw = await asyncio.to_thread(self._request, "DELETE", f"/orders/{broker_order_id}")
        return _result_from_raw(broker_order_id, raw, message="Dhan cancel request completed.")

    async def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        raw = await asyncio.to_thread(self._request, "GET", f"/orders/{broker_order_id}")
        return _result_from_raw(broker_order_id, raw, message="Dhan order status fetched.")

    async def get_positions(self) -> list[dict[str, Any]]:
        raw = await asyncio.to_thread(self._request, "GET", "/positions")
        return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))

    async def get_holdings(self) -> list[dict[str, Any]]:
        raw = await asyncio.to_thread(self._request, "GET", "/holdings")
        return _safe_raw(raw if isinstance(raw, list) else raw.get("data", raw))

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{DHAN_BASE_URL}{path}",
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
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else {}
        except HTTPError as exc:
            raise BrokerAdapterError(_map_http_error(exc)) from exc
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            raise BrokerAdapterError(f"broker request failed: {exc}") from exc


def _extract_order_id(raw: Any) -> str | None:
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
) -> BrokerOrderResult:
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    raw_status = data.get("orderStatus") or data.get("status")
    if not raw_status and isinstance(raw, dict):
        raw_status = raw.get("orderStatus")
    status = _normalize_status(str(raw_status or "pending"))
    quantity = int(data.get("quantity") or data.get("filledQty") or (fallback_order.quantity if fallback_order else 0) or 0)
    price = data.get("price") or data.get("averageTradedPrice") or (fallback_order.price if fallback_order else None)
    return BrokerOrderResult(
        broker_order_id=broker_order_id,
        status=status,
        symbol=str(data.get("tradingSymbol") or data.get("securityId") or (fallback_order.symbol if fallback_order else "")),
        side=str(data.get("transactionType") or (fallback_order.side if fallback_order else "")).upper(),
        quantity=quantity,
        price=float(price) if price not in {None, ""} else None,
        message=message,
        confirmed=status in {"pending", "transit", "open", "traded", "filled", "confirmed"},
        metadata={"raw_safe": _safe_raw(raw)},
    )


def _normalize_status(value: str) -> str:
    status = value.strip().lower().replace(" ", "_")
    if status in {"traded", "filled", "complete", "completed"}:
        return "filled"
    if status in {"pending", "transit", "open", "after_market_order_req_received"}:
        return "open"
    if status in {"rejected", "cancelled", "expired", "failed"}:
        return status
    return status or "pending"


def _map_http_error(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        payload = {}
    message = str(payload.get("remarks") or payload.get("message") or payload.get("errorMessage") or exc.reason or "")
    lower = message.lower()
    if exc.code in {401, 403}:
        return "token expired or invalid"
    if "margin" in lower or "fund" in lower:
        return "insufficient margin"
    if "market" in lower and "closed" in lower:
        return "market closed"
    if "reject" in lower:
        return f"order rejected: {message}"
    return f"broker rejected request: HTTP {exc.code} {message}".strip()


def _safe_raw(value: Any) -> Any:
    secret_keys = {"access-token", "access_token", "token", "authorization", "clientSecret", "apiSecret"}
    if isinstance(value, dict):
        return {key: ("[redacted]" if str(key).lower() in {item.lower() for item in secret_keys} else _safe_raw(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_raw(item) for item in value]
    return value
