"""Compatibility export for the canonical NSE option-chain provider.

Keeping this as a thin wrapper prevents the incomplete module split from
creating a second implementation with divergent safety behavior.
"""

from Backend.application.quant_modules import live_nse_option_chain

__all__ = ["live_nse_option_chain"]
