def _nse_index_symbol(symbol: str) -> str:
        normalized = symbol.upper().strip()
        aliases = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "MIDCPNIFTY": "MIDCPNIFTY",
        }
        return aliases.get(normalized, normalized)

    def _time_to_expiry(expiry: str | None) -> float:
        if not expiry:
            return 1 / 365

        try:
            expiry_dt = datetime.strptime(
                expiry,
                "%d-%b-%Y"
            ).replace(
                tzinfo=timezone.utc
            )

            seconds = (
                expiry_dt -
                datetime.now(timezone.utc)
            ).total_seconds()

            return max(seconds / (365 * 24 * 3600), 0.001)

        except Exception:
            return 1 / 365

    def _nse_number(value: Any) -> float | int | None:
        if value in {None, ""}:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        return int(number) if number.is_integer() else round(number, 4)


import concurrent.futures

def live_nse_option_chain(
    symbol: str = "NIFTY",
    *,
    strikes_each_side: int = 8,
    step: int = 50,
    ) -> dict[str, Any]:
    """Fetches real-time NSE options chain data, filters metrics, and constructs the processing payload."""
    nse_symbol = _nse_index_symbol(symbol)

    try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch_nse_option_chain, nse_symbol)
                payload = future.result(timeout=15)
    except Exception as exc:
            logger.exception("live_nse_option_chain_fetch_failed")
            observe_option_chain_failure(
                "nse",
                exc.__class__.__name__,
            )
            return _live_nse_fallback_payload(
                        option_chain_engine(
                        symbol,
                        strikes_each_side=strikes_each_side,
                        step=step,
                    ),
            exc,
            )

# Core data parsing extraction
    records = payload.get("records") or {}
    raw_rows = records.get("data") or []
    expiry = next((x for x in records.get("expiryDates") or [] if x), None)
    underlying = float(records.get("underlyingValue") or _latest_underlying_price(symbol))
    tte = _time_to_expiry(expiry)
    expiry_days = round(tte * 365, 2)
    atm = _round_to_step(underlying, step)
    lower = atm - strikes_each_side * step
    upper = atm + strikes_each_side * step

    rows = []

    for item in raw_rows:
        if expiry and item.get("expiryDate") != expiry:
            continue

        strike = int(item["strikePrice"])
        if strike < lower or strike > upper:
            continue

        ce = item.get("CE") or {}
        pe = item.get("PE") or {}
        ce_iv = max(float(ce.get("impliedVolatility") or 20) / 100, 0.01)
        pe_iv = max(float(pe.get("impliedVolatility") or 20) / 100, 0.01)
        
        rows.append({
            "strike": strike,
        "ce": {
                "ltp": _nse_number(ce.get("lastPrice")),
                "change":_nse_number(ce.get("change")),
                "volume": _nse_number(ce.get("totalTradedVolume")),
                "oi": _nse_number(ce.get("openInterest")),
                "iv": _nse_number(ce.get("impliedVolatility")),
                "oi_change": _nse_number(ce.get("changeinOpenInterest")),
                "greeks": _black_scholes_greeks(
                option_type="call",
                spot=underlying,
                strike=strike,
                time_to_expiry=tte,
                volatility=ce_iv,
                rate=0.06,
            ),
        },
            "pe": {
                    "ltp": _nse_number(pe.get("lastPrice")),
                    "change": _nse_number(pe.get("change")),
                    "volume": _nse_number(pe.get("totalTradedVolume")),
                    "oi": _nse_number(pe.get("openInterest")),
                    "iv": _nse_number(pe.get("impliedVolatility")),
                    "oi_change": _nse_number(pe.get("changeinOpenInterest")),
                    "greeks": _black_scholes_greeks(
                                    option_type="put",
                                    spot=underlying,
                                    strike=strike,
                                    time_to_expiry=tte,
                                    volatility=pe_iv,
                                    rate=0.06,
                                ),
                            },
                    })

                    # PERFORMANCE FIX: Sort the complete rows array ONCE outside the collection loop
        rows = sorted(rows, key=lambda row: int(cast(dict[str, Any], row).get("strike") or 0))

        if not rows:
            empty_chain_error = RuntimeError("NSE returned empty option chain")
            observe_option_chain_failure(
                "nse",
                empty_chain_error.__class__.__name__,
            )
            return _live_nse_fallback_payload(
            option_chain_engine(
                symbol,
                strikes_each_side=strikes_each_side,
                step=step,
            ),
            empty_chain_error,
        )

                # Compile tracking aggregates and analytical indicators
        typed_rows = cast(list[dict[str, Any]], rows)   
        total_call_oi = sum(float((r.get("ce") or {}).get("oi") or 0) for r in typed_rows)
        total_put_oi = sum(float((r.get("pe") or {}).get("oi") or 0) for r in typed_rows)
        total_call_oi_change = sum(float((r.get("ce") or {}).get("oi_change") or 0) for r in typed_rows)
        total_put_oi_change = sum(float((r.get("pe") or {}).get("oi_change") or 0) for r in typed_rows)

        pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi else None
        max_pain = _max_pain(rows)

                    # Return unified payload format back to engine caller
        return {
                        "underlying_price": underlying,
                        "atm_strike": atm,
                        "expiry_days": expiry_days,
                        "pcr": pcr,
                        "max_pain": max_pain,
                        "total_call_oi": total_call_oi,
                        "total_put_oi": total_put_oi,
                        "total_call_oi_change": total_call_oi_change,
                        "total_put_oi_change": total_put_oi_change,
                        "data": rows
                    }

# -------------------------------------------------
#        Build professional signal
# -------------------------------------------------
    signal_data = _professional_option_signal(
                rows,
                spot=underlying,
                atm=atm,
                pcr=pcr,
                max_pain=max_pain,
        )
        # -------------------------------------------------
        #           SUCCESS PAYLOAD
        # -------------------------------------------------
    return _option_chain_compat_payload(
                
            {
                "module": "live_nse_option_chain",
                "symbol": symbol.upper(),
                "underlying_price": underlying,
                "atm_strike": atm,
                "expiry": expiry,
                "step": step,
                "rows": rows,
                "pcr": pcr,
                "max_pain": max_pain,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "total_call_oi_change": total_call_oi_change,
                "total_put_oi_change": total_put_oi_change,
                "source": "live-nse-chain",
                "provider_available": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "expiry_days": expiry_days,
                "signal": signal_data["signal"],
                "signals": signal_data,
            })
