from __future__ import annotations

import asyncio
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from test_sqlalchemy_trading_stores import reset_backend_modules


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _configure(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "client-1")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token-1")
    monkeypatch.setenv("DHAN_SECURITY_ID_NIFTY", "26000")
    reset_backend_modules()


def test_dhan_place_order_requires_broker_confirmed_order_id(monkeypatch):
    _configure(monkeypatch)
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    def fake_urlopen(request, timeout):
        assert request.headers["Access-token"] == "token-1"
        return _Response({"orderId": "DHAN-1", "orderStatus": "TRANSIT", "access-token": "secret"})

    monkeypatch.setattr(dhan_order_adapter, "urlopen", fake_urlopen)
    result = asyncio.run(dhan_order_adapter.DhanBrokerClient().place_order(Order(symbol="NIFTY", side="BUY", quantity=25, price=100)))

    assert result.broker_order_id == "DHAN-1"
    assert result.status == "open"
    assert result.confirmed is True
    assert result.metadata["raw_safe"]["access-token"] == "[redacted]"


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("", "must be configured"),
        ("NIFTY", "must be numeric"),
        ("13", "index spot securityId is not tradable"),
    ],
)
def test_dhan_place_order_rejects_unsafe_security_id(monkeypatch, env_value, expected):
    _configure(monkeypatch)
    monkeypatch.setenv("DHAN_SECURITY_ID_NIFTY", env_value)
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    with pytest.raises(dhan_order_adapter.BrokerAdapterError, match=expected):
        asyncio.run(dhan_order_adapter.DhanBrokerClient().place_order(Order(symbol="NIFTY", side="BUY", quantity=75, price=100)))


@pytest.mark.parametrize(
    ("side", "quantity", "expected"),
    [
        ("HOLD", 75, "side must be BUY or SELL"),
        ("BUY", 0, "quantity must be greater than zero"),
    ],
)
def test_dhan_place_order_rejects_unsafe_order_shape(monkeypatch, side, quantity, expected):
    _configure(monkeypatch)
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    with pytest.raises(dhan_order_adapter.BrokerAdapterError, match=expected):
        asyncio.run(dhan_order_adapter.DhanBrokerClient().place_order(Order(symbol="NIFTY", side=side, quantity=quantity, price=100)))


def test_dhan_place_order_rejects_missing_order_id(monkeypatch):
    _configure(monkeypatch)
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(dhan_order_adapter, "urlopen", lambda *_args, **_kwargs: _Response({"orderStatus": "REJECTED"}))

    with pytest.raises(dhan_order_adapter.BrokerAdapterError, match="order rejected"):
        asyncio.run(dhan_order_adapter.DhanBrokerClient().place_order(Order(symbol="NIFTY", side="BUY", quantity=25)))


@pytest.mark.parametrize(
    ("code", "payload", "expected"),
    [
        (401, {"message": "invalid token"}, "token expired"),
        (400, {"remarks": "insufficient margin available"}, "insufficient margin"),
        (400, {"remarks": "market is closed"}, "market closed"),
        (400, {"remarks": "order rejected by exchange"}, "order rejected"),
    ],
)
def test_dhan_maps_clear_broker_errors(monkeypatch, code, payload, expected):
    _configure(monkeypatch)
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    def fake_urlopen(*_args, **_kwargs):
        raise HTTPError("https://api.dhan.co/v2/orders", code, "bad", {}, BytesIO(json.dumps(payload).encode("utf-8")))

    monkeypatch.setattr(dhan_order_adapter, "urlopen", fake_urlopen)

    with pytest.raises(dhan_order_adapter.BrokerAdapterError, match=expected):
        asyncio.run(dhan_order_adapter.DhanBrokerClient().place_order(Order(symbol="NIFTY", side="BUY", quantity=25)))


def test_dhan_positions_and_holdings_are_sanitized(monkeypatch):
    _configure(monkeypatch)
    from Backend.infrastructure.broker import dhan_order_adapter

    responses = {
        "/positions": {"data": [{"tradingSymbol": "NIFTY", "netQty": 25, "access_token": "secret"}]},
        "/holdings": [{"tradingSymbol": "INFY", "quantity": 1, "authorization": "secret"}],
    }

    def fake_urlopen(request, timeout):
        path = request.full_url.replace(dhan_order_adapter.DHAN_BASE_URL, "")
        return _Response(responses[path])

    monkeypatch.setattr(dhan_order_adapter, "urlopen", fake_urlopen)
    client = dhan_order_adapter.DhanBrokerClient()

    positions = asyncio.run(client.get_positions())
    holdings = asyncio.run(client.get_holdings())

    assert positions[0]["access_token"] == "[redacted]"
    assert holdings[0]["authorization"] == "[redacted]"
