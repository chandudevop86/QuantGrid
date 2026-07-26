from typing import Any


from Backend.domain.models.signal import StrategySignal
from Backend.application.trade_qualification_engine import TradeQualification

def _safe_float(value: Any) -> float | None:
    """
    Safely convert values to float.
    """

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None



def _paper_response(
    *,
    status_value: str,
    symbol: str,
    strategy: str | None,
    signal: StrategySignal | None,
    reason: str,
    execution_mode: str,
    strategy_diagnostics: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Standardized execution response builder.

    Used by:
    - paper trading
    - live validation
    - rejected executions
    - dry-run execution
    """

    response: dict[str, Any] = {

        # execution status
        "status": status_value,

        # instrument
        "symbol": (
            symbol.upper()
            if symbol
            else None
        ),

        # strategy metadata
        "strategy": strategy,

        # signal
        "signal": (
            str(signal.side).upper()
            if signal and signal.side
            else None
        ),


        # trade levels
        "entry": (
            _safe_float(signal.entry_price)
            if signal
            else None
        ),

        "stop": (
            _safe_float(signal.stop_loss)
            if signal
            else None
        ),

        "target": (
            _safe_float(signal.target_price)
            if signal
            else None
        ),


        # trailing
        "trailing_stop_loss": (
            _safe_float(
                signal.trailing_stop_loss
            )
            if signal
            else None
        ),

        "trailing_stop_pct": (
            _safe_float(
                signal.trailing_stop_pct
            )
            if signal
            else None
        ),


        # execution info
        "reason": reason,

        "execution_mode": execution_mode,


        # strategy analysis
        "strategy_diagnostics":
            strategy_diagnostics or {},


    }


    #
    # Attach additional execution fields
    #
    if extra:

        response.update(extra)



    #
    # Attach signal metadata safely
    #
    if signal:

        metadata = getattr(
            signal,
            "metadata",
            None,
        )


        if not isinstance(
            metadata,
            dict
        ):
            metadata = {}


        qualification = (
            metadata.get(
                "trade_qualification"
            )
        )


        if qualification is not None:

            response.setdefault(
                "trade_qualification",
                qualification,
            )


    return response