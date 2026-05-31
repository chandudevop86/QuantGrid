from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class MTFAValidation:
    valid: bool
    score: int
    grade: str
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class MTFAValidator:
    def validate(
        self,
        *,
        trend_aligned: bool,
        zone_touched: bool,
        confirmation_score: int,
        trigger_valid: bool,
        volume_confirmed: bool,
        rr: float,
        countertrend: bool,
    ) -> MTFAValidation:
        score = 0
        reasons: list[str] = []
        if trend_aligned:
            score += 3
            reasons.append("4H trend aligned")
        if zone_touched:
            score += 2
            reasons.append("4H zone touch")
        if confirmation_score > 0:
            score += min(2, confirmation_score)
            reasons.append("1H confirmation")
        if trigger_valid:
            score += 3
            reasons.append("15M trigger")
        if volume_confirmed:
            score += 1
            reasons.append("volume confirmation")
        if rr >= 3:
            score += 1
            reasons.append("RR above 3")
        grade = self.grade(score)
        confidence = score / 12 * 100
        valid = score >= 7 and rr >= 2 and (not countertrend or confidence > 95)
        if rr < 2:
            reasons.append("RR below 2")
        if countertrend and confidence <= 95:
            reasons.append("countertrend rejected")
        return MTFAValidation(valid, score, grade, reasons)

    @staticmethod
    def grade(score: int) -> str:
        if score >= 11:
            return "A+"
        if score >= 9:
            return "A"
        if score >= 7:
            return "B"
        if score >= 5:
            return "Watchlist"
        return "Reject"
