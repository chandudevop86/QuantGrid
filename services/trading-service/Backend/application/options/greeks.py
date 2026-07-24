def _norm_cdf(value: float) -> float:
        return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _norm_pdf(value: float) -> float:
        return exp(-0.5 * value * value) / sqrt(2.0 * 3.141592653589793)


def _black_scholes_greeks( *,
option_type: str,
spot: float,
strike: float,
time_to_expiry: float,
volatility: float,
rate: float,
dividend: float = 0.0
) -> dict[str, float]:
    spot = max(spot, 1e-9)
    strike = max(strike, 1e-9)

    sigma_sqrt_t = max(volatility * sqrt(max(time_to_expiry, 1e-6)), 1e-9)

    d1 = (
        log(spot / strike)
        + (rate - dividend + 0.5 * volatility ** 2)
        * time_to_expiry
        ) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    side = option_type.lower()
    delta = _norm_cdf(d1) if side == "call" else _norm_cdf(d1) - 1.0
    gamma = _norm_pdf(d1) / max(spot * sigma_sqrt_t, 1e-9)
    theta_call = (-(spot * _norm_pdf(d1) * volatility) / (2 * sqrt(max(time_to_expiry, 1e-6))) - rate * strike * exp(-rate * time_to_expiry) * _norm_cdf(d2)) / 365
    theta_put = (-(spot * _norm_pdf(d1) * volatility) / (2 * sqrt(max(time_to_expiry, 1e-6))) + rate * strike * exp(-rate * time_to_expiry) * _norm_cdf(-d2)) / 365
    vega = spot * _norm_pdf(d1) * sqrt(max(time_to_expiry, 1e-6)) / 100
    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta_call if side == "call" else theta_put, 4),
        "vega": round(vega, 4),
    }

