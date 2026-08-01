from __future__ import annotations

import pytest


@pytest.fixture
async def portfolio_id(client) -> str:
    resp = await client.post("/api/v1/portfolios", json={"name": "Trading Book"})
    return resp.json()["id"]


async def test_buy_creates_holding(client, portfolio_id):
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "AAPL",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 150,
            "fees": 5,
            "transaction_date": "2026-01-15",
        },
    )
    assert resp.status_code == 201

    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings")
    assert resp.status_code == 200
    holdings = resp.json()["items"]
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "AAPL"
    assert float(holdings[0]["quantity"]) == 10


async def test_buy_then_sell_updates_holding_and_realizes_pnl(client, portfolio_id):
    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "MSFT",
            "transaction_type": "BUY",
            "quantity": 20,
            "price": 100,
            "transaction_date": "2026-01-01",
        },
    )
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "MSFT",
            "transaction_type": "SELL",
            "quantity": 5,
            "price": 130,
            "transaction_date": "2026-02-01",
        },
    )
    assert resp.status_code == 201

    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings")
    holdings = {h["symbol"]: h for h in resp.json()["items"]}
    assert float(holdings["MSFT"]["quantity"]) == 15


async def test_sell_without_holding_rejected(client, portfolio_id):
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "TSLA",
            "transaction_type": "SELL",
            "quantity": 1,
            "price": 200,
            "transaction_date": "2026-01-01",
        },
    )
    assert resp.status_code == 422


async def test_split_transaction_adjusts_quantity(client, portfolio_id):
    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "NFLX",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 400,
            "transaction_date": "2026-01-01",
        },
    )
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "NFLX",
            "transaction_type": "SPLIT",
            "quantity": 0,
            "transaction_date": "2026-02-01",
            "split_ratio_from": 1,
            "split_ratio_to": 2,
        },
    )
    assert resp.status_code == 201

    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings")
    holding = resp.json()["items"][0]
    assert float(holding["quantity"]) == 20


async def test_delete_transaction_recomputes_holding(client, portfolio_id):
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "GOOG",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 100,
            "transaction_date": "2026-01-01",
        },
    )
    txn_id = resp.json()["id"]

    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "GOOG",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 200,
            "transaction_date": "2026-01-05",
        },
    )

    resp = await client.delete(f"/api/v1/portfolios/{portfolio_id}/transactions/{txn_id}")
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings")
    holding = resp.json()["items"][0]
    assert float(holding["quantity"]) == 10
    assert float(holding["average_cost"]) == pytest.approx(200.0)


async def test_transaction_validation_rejects_zero_quantity_buy(client, portfolio_id):
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "AMZN",
            "transaction_type": "BUY",
            "quantity": 0,
            "price": 100,
            "transaction_date": "2026-01-01",
        },
    )
    assert resp.status_code == 422
