def _live_nse_fallback_payload(
            payload: dict[str, Any],
            exc: Exception,
            ) -> dict[str, Any]:

                return _option_chain_compat_payload()
def _option_chain_compat_payload(payload: dict[str, Any]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = [
            row
            for row in (payload.get("rows") or [])
            if isinstance(row, dict)
        ]

        atm = payload.get("atm_strike")

        support = None
        resistance = None

        below = [
            row
            for row in rows
            if atm is not None
            and float(row.get("strike") or 0) < float(atm)
        ]

        above = [
            row
            for row in rows
            if atm is not None
            and float(row.get("strike") or 0) > float(atm)
        ]

        if below:
            support = max(
                below,
                key=lambda row: float(
                    (row.get("pe") or {}).get("oi") or 0
                ),
            ).get("strike")

        if above:
            resistance = max(
                above,
                key=lambda row: float(
                    (row.get("ce") or {}).get("oi") or 0
                ),
            ).get("strike")

        raw_pcr = payload.get("pcr")
        pcr = float(raw_pcr) if raw_pcr is not None else None

        max_pain = payload.get("max_pain")

        raw_spot = (
            payload.get("underlying_price")
            if payload.get("underlying_price") is not None
            else payload.get("spot")
        )

        spot = float(raw_spot) if raw_spot is not None else None

        signal_data = payload.get("signals")

        if not isinstance(signal_data, dict):
            signal_data = {
                "signal": "NO_TRADE",
                "bias": "NEUTRAL",
                "confidence": 0,
                "score": 0,
                "support": support,
                "resistance": resistance,
                "max_pain": max_pain,
                "reasons": ["Signal engine not executed"],
            }

        raw_source = str(payload.get("source") or "")

        source = (
            "live"
            if raw_source in {"live", "live-nse-chain"}
            else raw_source or "option-chain-unavailable"
        )

        return {
            **payload,
            "underlying": (
                payload.get("symbol")
                or payload.get("underlying")
                or "NIFTY"
            ),
            "spot": spot,
            "ATM": atm,
            "atm": atm,
            "PCR": pcr,
            "pcr": pcr,
            "support": support if support is not None else max_pain,
            "resistance": resistance if resistance is not None else max_pain,
            "source": source,
            "legacy_source": raw_source,
            "signal": signal_data.get("signal", "NO_TRADE"),
            "signals": signal_data,
        }
