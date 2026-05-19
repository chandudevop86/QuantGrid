from __future__ import annotations

from Backend.domain.smc.models import AMDContext, FVGZone, LiquiditySweep, ScoreBreakdown, SupplyDemandZone


class SMCScoringEngine:
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
        breakdown.amd_phase = 3 if amd.phase == "distribution" and amd.strength >= 1.5 else 2
        breakdown.liquidity_sweep = max(1, min(3, int(round(sweep.quality))))
        breakdown.fvg_validity = 3 if fvg.mitigated_index is not None else 2
        breakdown.zone_confluence = 2 if zone_overlaps_fvg and zone.touches <= 1 else 0
        breakdown.htf_alignment = 2 if htf_aligned else 0
        breakdown.entry_confirmation = 2 if entry_confirmation in {"rejection", "engulfing"} else 0
        breakdown.reasons = [
            f"AMD {amd.phase} confirmed after liquidity sweep",
            f"{sweep.side} stop hunt returned inside range",
            f"{fvg.side} FVG mitigated inside {zone.zone_type} zone",
            f"entry confirmation: {entry_confirmation or 'missing'}",
        ]
        return breakdown
