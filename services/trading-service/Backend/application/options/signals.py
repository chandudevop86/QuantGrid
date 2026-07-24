def _professional_option_signal(
            rows: list[dict[str, Any]],
                *,
                spot: float,
                atm: int,
                pcr: float | None,
                max_pain: int | None,

                ) -> dict[str, Any]:
                """
                Production option-chain signal engine.

                Returns
                -------
                {
                    signal,
                    confidence,
                    bias,
                    reasons,
                    support,
                    resistance
                }
                """

                if not rows:
                    return {
                        "signal": "NO_TRADE",
                        "bias": "NEUTRAL",
                        "confidence": 0,
                        "support": None,
                        "resistance": None,
                        "reasons": ["Empty option chain"],
                    }

                below = [r for r in rows if r["strike"] <= atm]
                above = [r for r in rows if r["strike"] >= atm]

                support = None
                resistance = None

                if below:
                    support = max(
                        below,
                        key=lambda x: float(x["pe"].get("oi") or 0)
                    )["strike"]

                if above:
                    resistance = max(
                        above,
                        key=lambda x: float(x["ce"].get("oi") or 0)
                    )["strike"]

                score = 0
                reasons = []

            ##########################################
            #             PCR
            ##########################################

                if pcr is not None:

                    if pcr >= 1.30:
                        score += 30
                        reasons.append("Bullish PCR")

                    elif pcr >= 1.10:
                        score += 15
                        reasons.append("Positive PCR")

                    elif pcr <= 0.70:
                        score -= 30
                        reasons.append("Bearish PCR")

                    elif pcr <= 0.90:
                        score -= 15
                        reasons.append("Weak PCR")

            ##########################################
                    # Max Pain
            ##########################################

                if max_pain is not None:

                    distance = abs(spot - max_pain)

                    if distance <= 50:
                        reasons.append("Near Max Pain")

                    if spot > max_pain:
                        score += 10
                        reasons.append("Above Max Pain")

                    elif spot < max_pain:
                        score -= 10
                        reasons.append("Below Max Pain")
                        
                    
            ##########################################
            # Support
            ##########################################

                if support:

                        if spot > support:
                            score += 15
                            reasons.append("Above Support")

                        else:
                            score -= 20
                            reasons.append("Support Broken")

            ##########################################
            # Resistance
            ##########################################

                if resistance:

                    if spot < resistance:
                        score += 5

                    else:
                        score -= 20
                        reasons.append("Resistance Breakout Failure")

            ##########################################
            # ATM Greeks
            ##########################################

                atm_row = next(
                    (
                        r
                        for r in rows
                        if r["strike"] == atm
                    ),
                    None,
                )

                if atm_row:

                    call_delta = float(
                        atm_row["ce"]["greeks"]["delta"]
                    )

                    put_delta = abs(
                        float(
                            atm_row["pe"]["greeks"]["delta"]
                        )
                    )

                    gamma = float(
                        atm_row["ce"]["greeks"]["gamma"]
                    )

                    iv = float(
                        atm_row["ce"].get("iv") or 20
                    )

                    ##################################

                    if gamma > 0.0008:
                        score += 5
                        reasons.append("High Gamma")

                    ##################################

                    if iv < 15:
                        score += 5
                        reasons.append("Low IV")

                    elif iv > 30:
                        score -= 5
                        reasons.append("High IV")

                    ##################################

                    if call_delta > put_delta:
                        score += 5

                    else:
                        score -= 5

                ##########################################
                # Confidence
                ##########################################
                MAX_SCORE = 70
                confidence = min(
                    round(abs(score) / MAX_SCORE * 100),
                100,
                )

                ##########################################
                # Final Signal
                ##########################################

                if score >= 40:

                    signal = "BUY_CE"
                    bias = "BULLISH"

                elif score <= -40:

                    signal = "BUY_PE"
                    bias = "BEARISH"

                else:

                    signal = "NO_TRADE"
                    bias = "NEUTRAL"

                ##########################################

                return {

                    "signal": signal,
                    
                    "bias": bias,

                    "confidence": confidence,

                    "score": score,

                    "support": support,

                    "resistance": resistance,
                    
                    "max_pain": max_pain,
                    "reasons": reasons,
                }
