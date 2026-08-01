from __future__ import annotations

import pytest


async def _seed_portfolio_with_holdings(client, fake_redis) -> str:
    resp = await client.post("/api/v1/portfolios", json={"name": "Analytics Book"})
    portfolio_id = resp.json()["id"]

    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "AAPL",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 100,
            "transaction_date": "2026-01-01",
        },
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "JPM",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 50,
            "transaction_date": "2026-01-01",
        },
    )
    await client.patch(
        f"/api/v1/portfolios/{portfolio_id}/holdings/"
        + (await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings")).json()["items"][0]["id"],
        json={"sector": "Technology"},
    )

    await fake_redis.set("quantgrid:market:price:AAPL", "150")
    await fake_redis.set("quantgrid:market:price:JPM", "60")
    return portfolio_id


async def test_holdings_are_enriched_with_live_price(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings")
    assert resp.status_code == 200
    holdings = {h["symbol"]: h for h in resp.json()["items"]}
    assert float(holdings["AAPL"]["current_price"]) == 150.0
    assert float(holdings["AAPL"]["market_value"]) == 1500.0


async def test_sector_allocation_endpoint(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/sector-allocation")
    assert resp.status_code == 200
    slices = resp.json()["slices"]
    total_weight = sum(s["weight_percent"] for s in slices)
    assert total_weight == pytest.approx(100.0, abs=0.01)


async def test_top_holdings_endpoint(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/top-holdings?limit=1")
    assert resp.status_code == 200
    holdings = resp.json()["holdings"]
    assert holdings[0]["label"] == "AAPL"  # AAPL has larger market value (1500 vs 600)


async def test_diversification_score_endpoint(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/diversification-score")
    assert resp.status_code == 200
    assert 0 <= resp.json()["diversification_score"] <= 100


async def test_health_score_endpoint(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/health-score")
    assert resp.status_code == 200
    assert 0 <= resp.json()["overall_score"] <= 100


async def test_rebalancing_suggestions_endpoint(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/rebalancing/suggestions",
        json={"target_weights": {"AAPL": 50, "JPM": 50}, "drift_tolerance_percent": 1.0},
    )
    assert resp.status_code == 200
    suggestions = {s["symbol"]: s for s in resp.json()["suggestions"]}
    # AAPL is overweight (1500 of 2100 ~ 71%), JPM underweight (600 of 2100 ~ 29%)
    assert suggestions["AAPL"]["action"] == "SELL"
    assert suggestions["JPM"]["action"] == "BUY"


async def test_portfolio_summary_endpoint(client, fake_redis):
    portfolio_id = await _seed_portfolio_with_holdings(client, fake_redis)
    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["holdings_count"] == 2
    assert float(body["total_market_value"]) == pytest.approx(2100.0)
