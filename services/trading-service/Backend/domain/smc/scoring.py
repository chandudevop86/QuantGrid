from __future__ import annotations

from Backend.domain.smc.models import (
    AMDContext,
    FVGZone,
    LiquiditySweep,
    ScoreBreakdown,
    SupplyDemandZone,
)


class SMCScoringEngine:
    """
    Computes the confluence score for an AMD + FVG + Supply/Demand setup.

    Maximum Score = 15

        AMD Phase             : 3
        Liquidity Sweep       : 3
        FVG Validity          : 3
        Zone Confluence       : 2
        HTF Alignment         : 2
        Entry Confirmation    : 2
    """

    MAX_SCORE = 15

    def score(
        self,
        *,
        amd: AMDContext,
        sweep: LiquiditySweep,
        fvg: FVGZone,
        zone: SupplyDemandZone,
        zone_overlaps_fvg: bool,
        htf_aligned: bool,
        entry_confirmation: str | None,
    ) -> ScoreBreakdown:

        breakdown = ScoreBreakdown()

        # ---------------------------------------------------------
        # AMD Phase
        # ---------------------------------------------------------
        if amd.phase == "distribution" and amd.strength >= 1.5:
            breakdown.amd_phase = 3
        else:
            breakdown.amd_phase = 2

        # ---------------------------------------------------------
        # Liquidity Sweep
        # ---------------------------------------------------------
        breakdown.liquidity_sweep = max(
            1,
            min(3, int(round(sweep.quality)))
        )

        # ---------------------------------------------------------
        # Fair Value Gap
        # ---------------------------------------------------------
        breakdown.fvg_validity = (
            3 if fvg.mitigated_index is not None else 2
        )

        # ---------------------------------------------------------
        # Zone Confluence
        # ---------------------------------------------------------
        if zone_overlaps_fvg and zone.touches <= 1:
            breakdown.zone_confluence = 2
        else:
            breakdown.zone_confluence = 0

        # ---------------------------------------------------------
        # Higher Timeframe Alignment
        # ---------------------------------------------------------
        breakdown.htf_alignment = 2 if htf_aligned else 0

        # ---------------------------------------------------------
        # Entry Confirmation
        # ---------------------------------------------------------
        breakdown.entry_confirmation = (
            2
            if entry_confirmation in ("engulfing", "rejection")
            else 0
        )

        # ---------------------------------------------------------
        # Debug Reasons
        # ---------------------------------------------------------
        breakdown.reasons = [
            (
                f"AMD Phase: {amd.phase} "
                f"(Strength={amd.strength:.2f}) "
                f"Score={breakdown.amd_phase}/3"
            ),
            (
                f"Liquidity Sweep: "
                f"{sweep.side} "
                f"(Quality={sweep.quality:.2f}) "
                f"Score={breakdown.liquidity_sweep}/3"
            ),
            (
                f"FVG: "
                f"{'Mitigated' if fvg.mitigated_index is not None else 'Unmitigated'} "
                f"Score={breakdown.fvg_validity}/3"
            ),
            (
                f"Zone Confluence: "
                f"{'PASS' if zone_overlaps_fvg else 'FAIL'} "
                f"(Touches={zone.touches}) "
                f"Score={breakdown.zone_confluence}/2"
            ),
            (
                f"HTF Alignment: "
                f"{'PASS' if htf_aligned else 'FAIL'} "
                f"Score={breakdown.htf_alignment}/2"
            ),
            (
                f"Entry Confirmation: "
                f"{entry_confirmation or 'None'} "
                f"Score={breakdown.entry_confirmation}/2"
            ),
        ]

        return breakdown