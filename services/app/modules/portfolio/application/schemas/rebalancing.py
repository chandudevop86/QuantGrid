from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class RebalancingRequest(BaseModel):
    target_weights: dict[str, float] = Field(
        ..., description="Map of symbol -> target weight percent (0-100). Must sum to <= 100."
    )
    drift_tolerance_percent: float = Field(default=2.0, ge=0, le=50)

    @model_validator(mode="after")
    def _validate_weights(self) -> "RebalancingRequest":
        if not self.target_weights:
            raise ValueError("target_weights must not be empty.")
        total = sum(self.target_weights.values())
        if total > 100.0001:
            raise ValueError(f"target_weights must sum to <= 100 (got {total:.2f}).")
        for symbol, weight in self.target_weights.items():
            if weight < 0:
                raise ValueError(f"target weight for '{symbol}' cannot be negative.")
        return self


class RebalancingSuggestionResponse(BaseModel):
    symbol: str
    current_weight_percent: float
    target_weight_percent: float
    drift_percent: float
    action: str
    suggested_amount: float


class RebalancingResponse(BaseModel):
    portfolio_id: str
    suggestions: list[RebalancingSuggestionResponse]
