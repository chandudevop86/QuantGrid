from __future__ import annotations

from Backend.tools.check_database import _mask_database_url


def test_mask_database_url_hides_password():
    masked = _mask_database_url("postgresql+psycopg://quant:secret@localhost:5432/quantgrid")

    assert masked == "postgresql+psycopg://quant:***@localhost:5432/quantgrid"
    assert "secret" not in masked


def test_mask_database_url_leaves_passwordless_url():
    url = "sqlite:///./Backend/data/quantgrid.sqlite3"

    assert _mask_database_url(url) == url
