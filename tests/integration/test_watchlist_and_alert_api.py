from __future__ import annotations

import pytest


async def test_create_watchlist_with_items(client):
    resp = await client.post(
        "/api/v1/watchlists",
        json={"name": "Tech Watch", "items": [{"symbol": "aapl"}, {"symbol": "msft"}]},
    )
    assert resp.status_code == 201
    body = resp.json()
    symbols = {item["symbol"] for item in body["items"]}
    assert symbols == {"AAPL", "MSFT"}


async def test_add_and_remove_watchlist_item(client):
    resp = await client.post("/api/v1/watchlists", json={"name": "Growth Watch"})
    watchlist_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/watchlists/{watchlist_id}/items", json={"symbol": "nvda"})
    assert resp.status_code in (200, 201)
    assert any(i["symbol"] == "NVDA" for i in resp.json()["items"])

    resp = await client.delete(f"/api/v1/watchlists/{watchlist_id}/items/nvda")
    assert resp.status_code == 200
    assert not any(i["symbol"] == "NVDA" for i in resp.json()["items"])


async def test_create_target_price_alert(client):
    resp = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "aapl",
            "alert_type": "TARGET_PRICE",
            "direction": "ABOVE",
            "threshold_price": 200,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["status"] == "ACTIVE"


async def test_create_stop_loss_alert_and_list(client):
    await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "tsla",
            "alert_type": "STOP_LOSS",
            "direction": "BELOW",
            "threshold_price": 150,
        },
    )
    resp = await client.get("/api/v1/alerts?alert_type=STOP_LOSS")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["direction"] == "BELOW"


async def test_update_and_delete_alert(client):
    resp = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "amzn",
            "alert_type": "TARGET_PRICE",
            "direction": "ABOVE",
            "threshold_price": 300,
        },
    )
    alert_id = resp.json()["id"]

    resp = await client.patch(f"/api/v1/alerts/{alert_id}", json={"threshold_price": 320})
    assert resp.status_code == 200
    assert float(resp.json()["threshold_price"]) == 320

    resp = await client.delete(f"/api/v1/alerts/{alert_id}")
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/alerts/{alert_id}")
    assert resp.status_code == 404
