from __future__ import annotations

from Backend.application.quant_modules import option_chain_engine


class OptionContractResolver:

    def resolve(
        self,
        *,
        symbol: str,
        option_type: str,
        strike_type: str = "ATM",
        expiry_type: str = "WEEKLY",
    ):

        payload = option_chain_engine(symbol)

        expiry = payload["expiry"]
        atm = payload["atm_strike"]

        rows = payload["rows"]

        for row in rows:

            if row["strike"] != atm:
                continue

            leg = row["ce"] if option_type == "CE" else row["pe"]

            return {
                "security_id": leg.get("security_id"),
                "strike": row["strike"],
                "expiry": expiry,
                "option_type": option_type,
                "instrument_type": "OPTIDX",
            }

        raise RuntimeError("ATM option contract not found")