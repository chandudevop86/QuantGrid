from datetime import datetime, timedelta, timezone

import pytest

from Backend.infrastructure.market_data import dhan_option_execution as provider


def quote_payload(now):
    return {"status": "success", "data": {"NSE_FNO": {"12345": {
        "last_trade_time": now.astimezone(provider.IST).strftime("%d/%m/%Y %H:%M:%S"),
        "depth": {"buy": [{"price": 49, "quantity": 130}, {"price": 0, "quantity": 0}],
                  "sell": [{"price": 50, "quantity": 65}, {"price": 0, "quantity": 0}]},
    }}}}


def test_quote_keeps_provider_time_and_skips_empty_depth_levels():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    quote = provider.parse_quote("12345", quote_payload(now), now=now)
    assert quote["ask"] == 50
    assert quote["bid"] == 49
    assert quote["ask_quantity"] == 65
    assert datetime.fromisoformat(quote["quote_timestamp"]) == now


def test_stale_quote_never_uses_request_time():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with pytest.raises(ValueError):
        provider.parse_quote("12345", quote_payload(now - timedelta(minutes=5)), now=now)


def test_quote_contract_identity_must_match():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="identity"):
        provider.parse_quote("23456", quote_payload(now), now=now)


def test_master_download_fields_verify_actual_contract_lot():
    expiry = (datetime.now(provider.IST) + timedelta(days=5)).date().isoformat()
    text = "EXCH_ID,SEGMENT,INSTRUMENT,UNDERLYING_SYMBOL,SECURITY_ID,LOT_SIZE,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE\n"
    text += f"NSE,D,OPTIDX,NIFTY,12345,65,{expiry},25000,CE\n"
    text += f"NSE,D,OPTIDX,BANKNIFTY,23456,35,{expiry},55000,CE\n"
    rows = provider.parse_master(text)
    assert len(rows) == 1
    assert rows[0]["security_id"] == "12345"
    assert rows[0]["lot_size"] == 65
    assert provider.select_contract(25010, "CE", rows=rows)["strike"] == 25000
