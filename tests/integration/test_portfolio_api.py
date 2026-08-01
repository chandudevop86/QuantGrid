from __future__ import annotations

import pytest


async def test_create_and_get_portfolio(client):
    resp = await client.post("/api/v1/portfolios", json={"name": "Retirement Fund"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Retirement Fund"
    portfolio_id = body["id"]

    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == portfolio_id


async def test_create_duplicate_name_conflicts(client):
    await client.post("/api/v1/portfolios", json={"name": "Growth"})
    resp = await client.post("/api/v1/portfolios", json={"name": "Growth"})
    assert resp.status_code == 409


async def test_list_portfolios_paginated(client):
    for i in range(3):
        await client.post("/api/v1/portfolios", json={"name": f"Portfolio {i}"})
    resp = await client.get("/api/v1/portfolios?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["meta"]["total_items"] == 3
    assert body["meta"]["has_next"] is True


async def test_update_portfolio(client):
    resp = await client.post("/api/v1/portfolios", json={"name": "Old Name"})
    portfolio_id = resp.json()["id"]

    resp = await client.patch(f"/api/v1/portfolios/{portfolio_id}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


async def test_delete_portfolio(client):
    resp = await client.post("/api/v1/portfolios", json={"name": "Temp"})
    portfolio_id = resp.json()["id"]

    resp = await client.delete(f"/api/v1/portfolios/{portfolio_id}")
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert resp.status_code == 404


async def test_get_nonexistent_portfolio_returns_404(client):
    resp = await client.get("/api/v1/portfolios/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_unauthenticated_request_rejected(client):
    resp = await client.post(
        "/api/v1/portfolios", json={"name": "No Auth"}, headers={"Authorization": ""}
    )
    assert resp.status_code == 401
