class TradingEngineBasketLeg(BaseModel):
    """
    Single basket order leg.
    """

    strategy: str = Field(
        default="manual_basket",
        min_length=1,
        max_length=100,
    )

    symbol: str = Field(
        default="NIFTY",
        min_length=1,
        max_length=30,
    )

    side: Literal["BUY", "SELL"] = "BUY"

    quantity: int = Field(
        default=1,
        gt=0,
        le=100000,
    )

    entry: float = Field(
        gt=0,
        description="Entry price",
    )

    stop_loss: float = Field(
        gt=0,
        description="Stop-loss price",
    )

    target: float = Field(
        gt=0,
        description="Target price",
    )

    trailing_stop_loss: float | None = Field(
        default=None,
        gt=0,
    )

    trailing_stop_pct: float | None = Field(
        default=None,
        gt=0,
        le=100,
    )

    score: float = Field(
        default=0.0,
        ge=0,
        le=100,
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("Symbol cannot be empty.")

        return value

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_trade_prices(self):
        if self.side == "BUY":
            if self.stop_loss >= self.entry:
                raise ValueError(
                    "BUY order: stop_loss must be below entry."
                )

            if self.target <= self.entry:
                raise ValueError(
                    "BUY order: target must be above entry."
                )

        else:  # SELL

            if self.stop_loss <= self.entry:
                raise ValueError(
                    "SELL order: stop_loss must be above entry."
                )

            if self.target >= self.entry:
                raise ValueError(
                    "SELL order: target must be below entry."
                )

        if (
            self.trailing_stop_loss is not None
            and self.trailing_stop_loss <= 0
        ):
            raise ValueError(
                "Trailing stop-loss must be greater than zero."
            )

        return self
    class TradingEngineBasketRequest(BaseModel):
    """
    Basket order execution request.
    """

    execution_mode: Literal["paper", "live"] = Field(
        default="paper",
        description="Execution mode.",
    )

    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for basket execution.",
    )

    legs: list[TradingEngineBasketLeg] = Field(
        default_factory=list,
        min_length=1,
        max_length=50,
        description="Basket order legs.",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None



class TradingEngineScaleRequest(BaseModel):
    """
    Request model for scaling an existing position.
    """

    execution_mode: Literal["paper", "live"] = Field(
        default="paper",
        description="Execution mode.",
    )

    action: Literal[
        "scale_in",
        "scale_out",
        "increase",
        "decrease",
    ] = Field(
        description="Scaling action.",
    )

    quantity: int = Field(
        gt=0,
        le=100000,
        description="Quantity to scale.",
    )

    price: float | None = Field(
        default=None,
        gt=0,
        description="Execution price (optional).",
    )

    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for scaling.",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

