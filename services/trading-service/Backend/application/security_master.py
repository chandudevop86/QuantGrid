"""
Backend/application/security_master.py

Dhan Security Master Resolver

Responsibilities
----------------
* Load Dhan Security Master CSV
* Resolve Symbol -> Security ID
* Return exchange segment
* Return instrument
* Return lot size
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


class SecurityMaster:

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self.df = pd.read_csv(
            self.csv_path,
            dtype=str,
            low_memory=False,
        )
        self.df.columns = [c.strip() for c in self.df.columns]

    def resolve(
        self,
        symbol: str,
        expiry: Optional[str] = None,
        strike: Optional[int] = None,
        option_type: Optional[str] = None,
    ) -> dict:
        symbol = symbol.upper()
        df = self.df.copy()
        df["SEM_TRADING_SYMBOL"] = (df["SEM_TRADING_SYMBOL"].fillna("").astype(str).str.upper())

        # Prefer exact match
        exact = df[df["SEM_TRADING_SYMBOL"] == symbol]

        if not exact.empty:
            df = exact
        else:
            df = df[df["SEM_TRADING_SYMBOL"].str.startswith(symbol)]

        if expiry:
            df = df[df["SEM_EXPIRY_DATE"] == expiry]

        if strike:
            df = df[df["SEM_STRIKE_PRICE"] == strike]

        if option_type:
            df = df[
                df["SEM_OPTION_TYPE"]
                .str.upper()
                .eq(option_type.upper())
            ]

        if df.empty:
            raise ValueError(f"Security not found: {symbol}")

        row = df.iloc[0]

        return {
            "security_id": str(row["SEM_SMST_SECURITY_ID"]),
            "exchange_segment": row["SEM_EXM_EXCH_ID"],
            "instrument": row["SEM_INSTRUMENT_NAME"],
            "symbol": row["SEM_TRADING_SYMBOL"],
            "lot_size": int(row["SEM_LOT_UNITS"]),
        }
