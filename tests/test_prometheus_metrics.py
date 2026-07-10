from conftest import admin_headers

def test_metrics_returns_prometheus_text(app_client):
    response = app_client.get("/metrics", headers=admin_headers(app_client))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP" in response.text
    assert "# TYPE" in response.text
    assert response.text.lstrip()[0] != "{"

