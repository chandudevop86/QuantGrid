from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from statistics import mean
from typing import Literal

from pydantic import BaseModel, Field

DISCLAIMER = "Educational research, not financial advice."


class InvestmentRecommendation(StrEnum):
    BUY = "BUY"
    HOLD = "HOLD"
    AVOID = "AVOID"
    WATCHLIST = "WATCHLIST"


class StockResearchInput(BaseModel):
    symbol: str
    name: str
    sector: str = "Diversified"
    revenue_growth_3y: float | None = None
    profit_growth_3y: float | None = None
    quarterly_revenue_growth: float | None = None
    quarterly_profit_growth: float | None = None
    debt_to_equity: float | None = None
    operating_cash_flow_positive: bool | None = None
    free_cash_flow_positive: bool | None = None
    roe: float | None = None
    roce: float | None = None
    promoter_holding: float | None = None
    fii_holding_change: float | None = None
    dii_holding_change: float | None = None
    pe: float | None = None
    sector_pe: float | None = None
    pb: float | None = None
    eps_growth: float | None = None
    dividend_years: int = 0
    sector_trend: Literal["positive", "neutral", "negative"] = "neutral"
    price_trend: Literal["uptrend", "sideways", "downtrend"] = "sideways"
    price_to_52w_high_pct: float = 0.0
    price_above_200dma: bool = False
    news_sentiment: Literal["positive", "neutral", "negative"] = "neutral"


class MutualFundInput(BaseModel):
    scheme_code: str
    name: str
    category: str
    nav: float = 0.0
    aum_cr: float = 0.0
    aum_growth_pct: float = 0.0
    expense_ratio: float = 0.0
    return_1y: float = 0.0
    return_3y: float = 0.0
    return_5y: float = 0.0
    category_return_1y: float = 0.0
    category_return_3y: float = 0.0
    category_return_5y: float = 0.0
    alpha: float = 0.0
    beta: float = 1.0
    sharpe: float = 0.0
    sortino: float = 0.0
    fund_manager_years: float = 0.0
    downside_capture: float = 100.0
    category_rank_percentile: float = 50.0
    return_consistency_years: int = 0


class DashboardCard(BaseModel):
    category: str
    name: str
    score: float
    recommendation: InvestmentRecommendation
    key_reason: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    allocation_suggestion: str


class MultibaggerPrediction(BaseModel):
    symbol: str
    name: str
    asset_type: Literal["multibagger_stock"] = "multibagger_stock"
    potential_score: float
    probability: int = Field(ge=0, le=100)
    rating: Literal["HIGH_POTENTIAL", "MODERATE_POTENTIAL", "LOW_POTENTIAL", "AVOID"]
    component_scores: dict[str, float]
    reason: str
    catalysts: list[str]
    risks: list[str]
    ideal_holding_period: str
    target_allocation: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    disclaimer: str = DISCLAIMER
    scored_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StockScore(BaseModel):
    symbol: str
    name: str
    asset_type: Literal["stock"] = "stock"
    total_score: float
    component_scores: dict[str, float]
    recommendation: InvestmentRecommendation
    confidence: int = Field(ge=0, le=100)
    reason: str
    risks: list[str]
    ideal_holding_period: str
    target_allocation: str
    dashboard_summary: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    disclaimer: str = DISCLAIMER
    scored_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MutualFundScore(BaseModel):
    scheme_code: str
    name: str
    asset_type: Literal["mutual_fund"] = "mutual_fund"
    total_score: float
    component_scores: dict[str, float]
    recommendation: InvestmentRecommendation
    confidence: int = Field(ge=0, le=100)
    reason: str
    risks: list[str]
    ideal_holding_period: str
    target_allocation: str
    dashboard_summary: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    category_comparison: str
    disclaimer: str = DISCLAIMER
    scored_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _weighted_score(raw_percent: float, weight: float) -> float:
    return round(_clamp(raw_percent) * weight / 100, 2)


def _metric(value: float | int | None, default: float = 0.0) -> float:
    return default if value is None else float(value)


def _flag(value: bool | None, default: bool = False) -> bool:
    return default if value is None else bool(value)


def _missing_stock_fields(stock: StockResearchInput) -> list[str]:
    required = [
        "revenue_growth_3y",
        "profit_growth_3y",
        "quarterly_revenue_growth",
        "quarterly_profit_growth",
        "debt_to_equity",
        "operating_cash_flow_positive",
        "free_cash_flow_positive",
        "roe",
        "roce",
        "pe",
        "pb",
        "eps_growth",
    ]
    return [field for field in required if getattr(stock, field) is None]


def _risk_level(score: float, risks: list[str]) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if score < 50 or any(
        marker in risk.lower()
        for risk in risks
        for marker in ("high debt", "weak cash flow", "risk-adjusted return is weak", "downside participation")
    ):
        return "HIGH"
    if score < 70 or len(risks) >= 2:
        return "MEDIUM"
    return "LOW"


def _stock_components(stock: StockResearchInput) -> dict[str, float]:
    revenue_growth_3y = _metric(stock.revenue_growth_3y)
    profit_growth_3y = _metric(stock.profit_growth_3y)
    quarterly_revenue_growth = _metric(stock.quarterly_revenue_growth)
    quarterly_profit_growth = _metric(stock.quarterly_profit_growth)
    debt_to_equity = _metric(stock.debt_to_equity, 2.0)
    operating_cash_flow_positive = _flag(stock.operating_cash_flow_positive)
    free_cash_flow_positive = _flag(stock.free_cash_flow_positive)
    roe = _metric(stock.roe)
    roce = _metric(stock.roce)
    promoter_holding = _metric(stock.promoter_holding)
    fii_holding_change = _metric(stock.fii_holding_change)
    dii_holding_change = _metric(stock.dii_holding_change)
    pe = _metric(stock.pe)
    sector_pe = _metric(stock.sector_pe)
    pb = _metric(stock.pb, 10.0)
    eps_growth = _metric(stock.eps_growth)
    growth_raw = (
        _clamp(revenue_growth_3y * 2.0)
        + _clamp(profit_growth_3y * 2.0)
        + _clamp(quarterly_revenue_growth * 2.5)
        + _clamp(quarterly_profit_growth * 2.5)
        + _clamp(eps_growth * 2.0)
    ) / 5
    profitability_raw = (
        _clamp(roe * 3.0)
        + _clamp(roce * 2.5)
        + (100 if operating_cash_flow_positive else 20)
        + (100 if free_cash_flow_positive else 20)
    ) / 4
    pe_discount = 100 if sector_pe <= 0 else _clamp((sector_pe - pe) / sector_pe * 100 + 55)
    valuation_raw = (pe_discount + _clamp((8 - pb) * 12.5) + _clamp(eps_growth * 2.0)) / 3
    balance_raw = (
        _clamp((1.5 - debt_to_equity) / 1.5 * 100)
        + (100 if operating_cash_flow_positive else 10)
        + _clamp(promoter_holding * 1.5)
        + _clamp((fii_holding_change + dii_holding_change + 4) * 12.5)
    ) / 4
    technical_raw = mean(
        [
            100 if stock.price_trend == "uptrend" else 55 if stock.price_trend == "sideways" else 20,
            100 if stock.price_above_200dma else 35,
            _clamp(100 - abs(stock.price_to_52w_high_pct - 12) * 3),
            100 if stock.sector_trend == "positive" else 55 if stock.sector_trend == "neutral" else 20,
        ]
    )
    sentiment_raw = mean(
        [
            100 if stock.news_sentiment == "positive" else 55 if stock.news_sentiment == "neutral" else 15,
            _clamp(stock.dividend_years * 12),
            _clamp((fii_holding_change + dii_holding_change + 4) * 12.5),
        ]
    )
    return {
        "growth": _weighted_score(growth_raw, 25),
        "profitability": _weighted_score(profitability_raw, 20),
        "valuation": _weighted_score(valuation_raw, 20),
        "balance_sheet_strength": _weighted_score(balance_raw, 15),
        "technical_trend": _weighted_score(technical_raw, 10),
        "sentiment_news": _weighted_score(sentiment_raw, 10),
    }


def _stock_risks(stock: StockResearchInput) -> list[str]:
    risks: list[str] = []
    missing = _missing_stock_fields(stock)
    if missing:
        risks.append(f"Missing fundamentals: {', '.join(missing)}.")
    revenue_growth_3y = _metric(stock.revenue_growth_3y)
    profit_growth_3y = _metric(stock.profit_growth_3y)
    debt_to_equity = _metric(stock.debt_to_equity, 2.0)
    operating_cash_flow_positive = _flag(stock.operating_cash_flow_positive)
    free_cash_flow_positive = _flag(stock.free_cash_flow_positive)
    pe = _metric(stock.pe)
    sector_pe = _metric(stock.sector_pe)
    if debt_to_equity > 1.2:
        risks.append("High debt/equity can pressure long-term compounding.")
    if not operating_cash_flow_positive or not free_cash_flow_positive:
        risks.append("Weak cash flow reduces investment quality.")
    if revenue_growth_3y < 8 or profit_growth_3y < 8:
        risks.append("Revenue or profit growth is not yet consistent.")
    if sector_pe > 0 and pe > sector_pe * 1.25:
        risks.append("Valuation is stretched versus sector average.")
    if stock.news_sentiment == "negative":
        risks.append("News sentiment is negative.")
    if stock.price_trend == "downtrend":
        risks.append("Price trend is weak; avoid relying on price alone.")
    return risks


def score_stock(stock: StockResearchInput) -> StockScore:
    components = _stock_components(stock)
    missing = _missing_stock_fields(stock)
    total = round(max(0.0, sum(components.values()) - len(missing) * 2.0), 2)
    risks = _stock_risks(stock)
    sector_pe = _metric(stock.sector_pe)
    pe = _metric(stock.pe)
    debt_to_equity = _metric(stock.debt_to_equity, 2.0)
    operating_cash_flow_positive = _flag(stock.operating_cash_flow_positive)
    free_cash_flow_positive = _flag(stock.free_cash_flow_positive)
    overvalued = sector_pe > 0 and pe > sector_pe * 1.25
    high_debt_or_cashflow = debt_to_equity > 1.2 or not operating_cash_flow_positive or not free_cash_flow_positive

    if high_debt_or_cashflow and total < 72:
        recommendation = InvestmentRecommendation.AVOID
    elif overvalued:
        recommendation = InvestmentRecommendation.WATCHLIST if total >= 65 else InvestmentRecommendation.AVOID
    elif not missing and total >= 70 and components["growth"] >= 9 and components["profitability"] >= 16 and len(risks) <= 1:
        recommendation = InvestmentRecommendation.BUY
    elif total >= 62:
        recommendation = InvestmentRecommendation.HOLD
    elif total >= 50:
        recommendation = InvestmentRecommendation.WATCHLIST
    else:
        recommendation = InvestmentRecommendation.AVOID

    confidence = int(_clamp(total - len(risks) * 4 + (8 if recommendation == InvestmentRecommendation.BUY else 0), 35, 95))
    risk_level = _risk_level(total, risks)
    reason_bits = [
        f"{stock.name} scores {total:.1f}/100",
        f"growth {components['growth']:.1f}/25",
        f"profitability {components['profitability']:.1f}/20",
        f"valuation {components['valuation']:.1f}/20",
    ]
    if overvalued:
        reason_bits.append("flagged as overvalued versus sector")
    if high_debt_or_cashflow:
        reason_bits.append("balance-sheet/cash-flow quality needs caution")

    return StockScore(
        symbol=stock.symbol.upper(),
        name=stock.name,
        total_score=total,
        component_scores=components,
        recommendation=recommendation,
        confidence=confidence,
        reason="; ".join(reason_bits) + ".",
        risks=risks or ["No major model risk flag from supplied inputs."],
        ideal_holding_period="3-5 years" if recommendation in {InvestmentRecommendation.BUY, InvestmentRecommendation.HOLD} else "Review after next 1-2 quarters",
        target_allocation="4-6%" if recommendation == InvestmentRecommendation.BUY else "2-3%" if recommendation == InvestmentRecommendation.HOLD else "0-2%",
        dashboard_summary=f"{recommendation.value}: {stock.sector} compounder screen at {total:.1f}/100. {DISCLAIMER}",
        risk_level=risk_level,
    )


def _multibagger_components(stock: StockResearchInput) -> dict[str, float]:
    revenue_growth_3y = _metric(stock.revenue_growth_3y)
    profit_growth_3y = _metric(stock.profit_growth_3y)
    quarterly_revenue_growth = _metric(stock.quarterly_revenue_growth)
    quarterly_profit_growth = _metric(stock.quarterly_profit_growth)
    eps_growth = _metric(stock.eps_growth)
    roe = _metric(stock.roe)
    roce = _metric(stock.roce)
    debt_to_equity = _metric(stock.debt_to_equity, 2.0)
    operating_cash_flow_positive = _flag(stock.operating_cash_flow_positive)
    free_cash_flow_positive = _flag(stock.free_cash_flow_positive)
    sector_pe = _metric(stock.sector_pe)
    pe = _metric(stock.pe)
    pb = _metric(stock.pb, 10.0)
    promoter_holding = _metric(stock.promoter_holding)
    fii_holding_change = _metric(stock.fii_holding_change)
    dii_holding_change = _metric(stock.dii_holding_change)
    growth_runway_raw = mean(
        [
            _clamp(revenue_growth_3y * 3.0),
            _clamp(profit_growth_3y * 3.0),
            _clamp(quarterly_revenue_growth * 3.0),
            _clamp(quarterly_profit_growth * 3.0),
            _clamp(eps_growth * 3.0),
        ]
    )
    reinvestment_quality_raw = mean(
        [
            _clamp(roe * 3.2),
            _clamp(roce * 3.0),
            100 if operating_cash_flow_positive else 15,
            100 if free_cash_flow_positive else 20,
        ]
    )
    valuation_room_raw = mean(
        [
            100 if sector_pe <= 0 else _clamp((sector_pe - pe) / sector_pe * 100 + 60),
            _clamp((7 - pb) * 14),
            _clamp((eps_growth * 2.5) - max(pe - sector_pe, 0)),
        ]
    )
    balance_sheet_raw = mean(
        [
            _clamp((1.0 - debt_to_equity) * 100),
            100 if operating_cash_flow_positive else 10,
            100 if free_cash_flow_positive else 15,
        ]
    )
    ownership_raw = mean(
        [
            _clamp(promoter_holding * 1.6),
            _clamp((fii_holding_change + 3) * 16),
            _clamp((dii_holding_change + 3) * 16),
        ]
    )
    trend_raw = mean(
        [
            100 if stock.sector_trend == "positive" else 55 if stock.sector_trend == "neutral" else 15,
            100 if stock.price_trend == "uptrend" else 45 if stock.price_trend == "sideways" else 10,
            100 if stock.price_above_200dma else 30,
            _clamp(100 - max(stock.price_to_52w_high_pct - 25, 0) * 3),
        ]
    )
    return {
        "growth_runway": _weighted_score(growth_runway_raw, 25),
        "reinvestment_quality": _weighted_score(reinvestment_quality_raw, 20),
        "valuation_room": _weighted_score(valuation_room_raw, 15),
        "balance_sheet_safety": _weighted_score(balance_sheet_raw, 15),
        "ownership_support": _weighted_score(ownership_raw, 10),
        "trend_confirmation": _weighted_score(trend_raw, 15),
    }


def predict_multibagger_stock(stock: StockResearchInput) -> MultibaggerPrediction:
    components = _multibagger_components(stock)
    missing = _missing_stock_fields(stock)
    score = round(max(0.0, sum(components.values()) - len(missing) * 2.5), 2)
    risks = _stock_risks(stock)
    catalysts: list[str] = []

    revenue_growth_3y = _metric(stock.revenue_growth_3y)
    profit_growth_3y = _metric(stock.profit_growth_3y)
    roe = _metric(stock.roe)
    roce = _metric(stock.roce)
    debt_to_equity = _metric(stock.debt_to_equity, 2.0)
    operating_cash_flow_positive = _flag(stock.operating_cash_flow_positive)
    free_cash_flow_positive = _flag(stock.free_cash_flow_positive)
    sector_pe = _metric(stock.sector_pe)
    pe = _metric(stock.pe)
    fii_holding_change = _metric(stock.fii_holding_change)
    dii_holding_change = _metric(stock.dii_holding_change)

    if revenue_growth_3y >= 15 and profit_growth_3y >= 15:
        catalysts.append("Consistent revenue and profit growth above multibagger threshold.")
    if roe >= 18 and roce >= 18:
        catalysts.append("High ROE/ROCE suggests strong reinvestment economics.")
    if debt_to_equity <= 0.5 and operating_cash_flow_positive and free_cash_flow_positive:
        catalysts.append("Low leverage with positive operating and free cash flow.")
    if stock.sector_trend == "positive":
        catalysts.append("Sector trend is supportive.")
    if fii_holding_change > 0 or dii_holding_change > 0:
        catalysts.append("Institutional ownership trend is improving.")

    hard_block = debt_to_equity > 1.2 or not operating_cash_flow_positive or not free_cash_flow_positive
    overvalued = sector_pe > 0 and pe > sector_pe * 1.4
    if hard_block or missing:
        rating: Literal["HIGH_POTENTIAL", "MODERATE_POTENTIAL", "LOW_POTENTIAL", "AVOID"] = "AVOID"
    elif score >= 78 and len(risks) <= 1 and not overvalued:
        rating = "HIGH_POTENTIAL"
    elif score >= 65 and len(risks) <= 2:
        rating = "MODERATE_POTENTIAL"
    elif score >= 50:
        rating = "LOW_POTENTIAL"
    else:
        rating = "AVOID"

    if overvalued:
        risks.append("Multibagger upside may be capped by elevated valuation.")
    if stock.price_trend == "downtrend":
        risks.append("Technical trend has not confirmed accumulation.")
    if not catalysts:
        catalysts.append("No strong catalyst from supplied inputs.")

    probability = int(_clamp(score - len(risks) * 5 + (8 if rating == "HIGH_POTENTIAL" else 0), 20, 92))
    risk_level = _risk_level(score, risks)
    reason = (
        f"{stock.name} multibagger potential score is {score:.1f}/100; "
        f"growth runway {components['growth_runway']:.1f}/25, "
        f"reinvestment quality {components['reinvestment_quality']:.1f}/20, "
        f"valuation room {components['valuation_room']:.1f}/15."
    )
    return MultibaggerPrediction(
        symbol=stock.symbol.upper(),
        name=stock.name,
        potential_score=score,
        probability=probability,
        rating=rating,
        component_scores=components,
        reason=reason,
        catalysts=catalysts,
        risks=risks or ["No major multibagger risk flag from supplied inputs."],
        ideal_holding_period="5-10 years with quarterly thesis review",
        target_allocation="2-4%" if rating == "HIGH_POTENTIAL" else "1-2%" if rating == "MODERATE_POTENTIAL" else "0-1%",
        risk_level=risk_level,
    )


def _fund_components(fund: MutualFundInput) -> dict[str, float]:
    excess_1y = fund.return_1y - fund.category_return_1y
    excess_3y = fund.return_3y - fund.category_return_3y
    excess_5y = fund.return_5y - fund.category_return_5y
    long_term_raw = mean([_clamp((fund.return_3y + 4) * 4), _clamp((fund.return_5y + 4) * 4), _clamp((excess_3y + excess_5y + 8) * 6)])
    consistency_raw = mean([_clamp(fund.return_consistency_years * 20), _clamp((excess_1y + excess_3y + excess_5y + 9) * 8)])
    risk_adjusted_raw = mean([_clamp((fund.alpha + 4) * 12), _clamp(fund.sharpe * 45), _clamp(fund.sortino * 35), _clamp((1.2 - fund.beta) * 100), _clamp((120 - fund.downside_capture) * 2)])
    expense_raw = _clamp((2.5 - fund.expense_ratio) / 2.5 * 100)
    aum_raw = mean([_clamp(fund.aum_cr / 50), _clamp((fund.aum_growth_pct + 10) * 5)])
    manager_raw = _clamp(fund.fund_manager_years * 18)
    category_rank_raw = _clamp(100 - fund.category_rank_percentile)
    return {
        "long_term_returns": _weighted_score(long_term_raw, 25),
        "consistency": _weighted_score(consistency_raw, 20),
        "risk_adjusted_return": _weighted_score(risk_adjusted_raw, 20),
        "expense_ratio": _weighted_score(expense_raw, 10),
        "aum_stability": _weighted_score(aum_raw, 10),
        "fund_manager_quality": _weighted_score(manager_raw, 10),
        "category_rank": _weighted_score(category_rank_raw, 5),
    }


def _fund_risks(fund: MutualFundInput) -> list[str]:
    risks: list[str] = []
    if fund.expense_ratio > 1.5:
        risks.append("Expense ratio is high versus preferred long-term fund profile.")
    if fund.return_3y < fund.category_return_3y or fund.return_5y < fund.category_return_5y:
        risks.append("Returns lag category average.")
    if fund.sharpe < 0.8 or fund.sortino < 1.0:
        risks.append("Risk-adjusted return is weak.")
    if fund.beta > 1.15 or fund.downside_capture > 105:
        risks.append("Downside participation is elevated.")
    if fund.fund_manager_years < 2:
        risks.append("Fund manager history is short.")
    if fund.aum_cr < 500:
        risks.append("AUM is small; monitor liquidity and stability.")
    return risks


def score_mutual_fund(fund: MutualFundInput) -> MutualFundScore:
    components = _fund_components(fund)
    total = round(sum(components.values()), 2)
    risks = _fund_risks(fund)
    category_delta = mean(
        [
            fund.return_1y - fund.category_return_1y,
            fund.return_3y - fund.category_return_3y,
            fund.return_5y - fund.category_return_5y,
        ]
    )

    if fund.expense_ratio > 1.8 or fund.sharpe < 0.55 or fund.return_5y < fund.category_return_5y - 3:
        recommendation = InvestmentRecommendation.AVOID
    elif total >= 78 and category_delta > 0 and len(risks) <= 1:
        recommendation = InvestmentRecommendation.BUY
    elif total >= 65:
        recommendation = InvestmentRecommendation.HOLD
    elif total >= 52:
        recommendation = InvestmentRecommendation.WATCHLIST
    else:
        recommendation = InvestmentRecommendation.AVOID

    confidence = int(_clamp(total - len(risks) * 3 + (6 if category_delta > 0 else -4), 35, 94))
    risk_level = _risk_level(total, risks)
    comparison = "outperforming category average" if category_delta > 1 else "near category average" if category_delta > -1 else "underperforming category average"
    return MutualFundScore(
        scheme_code=fund.scheme_code,
        name=fund.name,
        total_score=total,
        component_scores=components,
        recommendation=recommendation,
        confidence=confidence,
        reason=(
            f"{fund.name} scores {total:.1f}/100 with {comparison}; "
            f"risk-adjusted score {components['risk_adjusted_return']:.1f}/20 and expense score {components['expense_ratio']:.1f}/10."
        ),
        risks=risks or ["No major model risk flag from supplied inputs."],
        ideal_holding_period="5+ years through SIP/STP cycles" if recommendation in {InvestmentRecommendation.BUY, InvestmentRecommendation.HOLD} else "Review after 2-3 factsheets",
        target_allocation="8-12%" if recommendation == InvestmentRecommendation.BUY else "4-8%" if recommendation == InvestmentRecommendation.HOLD else "0-3%",
        dashboard_summary=f"{recommendation.value}: {fund.category} fund at {total:.1f}/100, {comparison}. {DISCLAIMER}",
        risk_level=risk_level,
        category_comparison=comparison,
    )


def build_dashboard_card(category: str, score: StockScore | MutualFundScore | MultibaggerPrediction) -> DashboardCard:
    if isinstance(score, MultibaggerPrediction):
        recommendation = (
            InvestmentRecommendation.BUY
            if score.rating == "HIGH_POTENTIAL"
            else InvestmentRecommendation.WATCHLIST
            if score.rating in {"MODERATE_POTENTIAL", "LOW_POTENTIAL"}
            else InvestmentRecommendation.AVOID
        )
        return DashboardCard(
            category=category,
            name=score.name,
            score=score.potential_score,
            recommendation=recommendation,
            key_reason=score.reason,
            risk_level=score.risk_level,
            allocation_suggestion=score.target_allocation,
        )
    return DashboardCard(
        category=category,
        name=score.name,
        score=score.total_score,
        recommendation=score.recommendation,
        key_reason=score.reason,
        risk_level=score.risk_level,
        allocation_suggestion=score.target_allocation,
    )


def build_investment_dashboard(
    stock_scores: list[StockScore],
    fund_scores: list[MutualFundScore],
    multibagger_predictions: list[MultibaggerPrediction] | None = None,
) -> dict[str, object]:
    multibagger_predictions = multibagger_predictions or []
    top_stocks = [item for item in stock_scores if item.recommendation in {InvestmentRecommendation.BUY, InvestmentRecommendation.HOLD}]
    watchlist = [item for item in stock_scores if item.recommendation == InvestmentRecommendation.WATCHLIST]
    avoid_stocks = [item for item in stock_scores if item.recommendation == InvestmentRecommendation.AVOID]
    top_funds = [item for item in fund_scores if item.recommendation in {InvestmentRecommendation.BUY, InvestmentRecommendation.HOLD}]
    sip_ideas = [item for item in top_funds if item.risk_level in {"LOW", "MEDIUM"}]

    sector_counts: dict[str, int] = {}
    for stock in stock_scores:
        if stock.recommendation in {InvestmentRecommendation.BUY, InvestmentRecommendation.HOLD}:
            sector = stock.dashboard_summary.split(": ", 1)[-1].split(" compounder", 1)[0]
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
    sector_trend = sorted(sector_counts.items(), key=lambda item: item[1], reverse=True)
    risk_alerts = [score for score in [*stock_scores, *fund_scores] if score.risk_level == "HIGH"]

    cards = {
        "multibagger_candidates": [
            build_dashboard_card("Multibagger candidates", item)
            for item in sorted(
                [candidate for candidate in multibagger_predictions if candidate.rating in {"HIGH_POTENTIAL", "MODERATE_POTENTIAL"}],
                key=lambda value: value.potential_score,
                reverse=True,
            )[:5]
        ],
        "top_stock_picks": [build_dashboard_card("Top stock picks", item) for item in sorted(top_stocks, key=lambda value: value.total_score, reverse=True)[:5]],
        "watchlist_stocks": [build_dashboard_card("Watchlist stocks", item) for item in sorted(watchlist, key=lambda value: value.total_score, reverse=True)[:5]],
        "avoid_stocks": [build_dashboard_card("Avoid stocks", item) for item in sorted(avoid_stocks, key=lambda value: value.total_score)[:5]],
        "top_mutual_funds": [build_dashboard_card("Top mutual funds", item) for item in sorted(top_funds, key=lambda value: value.total_score, reverse=True)[:5]],
        "sip_ideas": [build_dashboard_card("SIP ideas", item) for item in sorted(sip_ideas, key=lambda value: value.total_score, reverse=True)[:5]],
        "sector_trend": [
            DashboardCard(
                category="Sector trend",
                name=sector,
                score=float(count),
                recommendation=InvestmentRecommendation.WATCHLIST,
                key_reason=f"{count} investable stock screen(s) from this sector.",
                risk_level="MEDIUM",
                allocation_suggestion="Diversify; avoid sector concentration above 20%.",
            )
            for sector, count in sector_trend[:5]
        ],
        "risk_alerts": [build_dashboard_card("Risk alerts", item) for item in risk_alerts[:7]],
    }

    summary = (
        f"{len(cards['multibagger_candidates'])} multibagger candidates, {len(cards['top_stock_picks'])} stock ideas, {len(cards['top_mutual_funds'])} mutual fund ideas, "
        f"{len(cards['risk_alerts'])} high-risk alerts. {DISCLAIMER}"
    )
    return {"cards": cards, "summary": summary, "disclaimer": DISCLAIMER}
