from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from app.investing.investment_research_loop import (
    InvestmentRecommendation,
    MutualFundInput,
    StockResearchInput,
    score_mutual_fund,
    score_stock,
)
from conftest import admin_headers


def _good_stock(**updates):
    payload = {
        "symbol": "QGGOOD",
        "name": "QuantGrid Quality Ltd",
        "sector": "Technology",
        "revenue_growth_3y": 18,
        "profit_growth_3y": 20,
        "quarterly_revenue_growth": 16,
        "quarterly_profit_growth": 18,
        "debt_to_equity": 0.1,
        "operating_cash_flow_positive": True,
        "free_cash_flow_positive": True,
        "roe": 28,
        "roce": 32,
        "promoter_holding": 58,
        "fii_holding_change": 1.1,
        "dii_holding_change": 0.8,
        "pe": 26,
        "sector_pe": 32,
        "pb": 4,
        "eps_growth": 18,
        "dividend_years": 8,
        "sector_trend": "positive",
        "price_trend": "uptrend",
        "price_to_52w_high_pct": 9,
        "price_above_200dma": True,
        "news_sentiment": "positive",
    }
    payload.update(updates)
    return StockResearchInput(**payload)


def _good_fund(**updates):
    payload = {
        "scheme_code": "QG-FUND",
        "name": "QuantGrid Compounding Fund",
        "category": "Flexi Cap",
        "nav": 145,
        "aum_cr": 9000,
        "aum_growth_pct": 14,
        "expense_ratio": 0.65,
        "return_1y": 20,
        "return_3y": 18,
        "return_5y": 17,
        "category_return_1y": 15,
        "category_return_3y": 14,
        "category_return_5y": 13,
        "alpha": 4,
        "beta": 0.92,
        "sharpe": 1.45,
        "sortino": 1.9,
        "fund_manager_years": 7,
        "downside_capture": 78,
        "category_rank_percentile": 10,
        "return_consistency_years": 5,
    }
    payload.update(updates)
    return MutualFundInput(**payload)


def test_good_stock_scores_buy_with_full_research_reason():
    score = score_stock(_good_stock())

    assert score.recommendation == InvestmentRecommendation.BUY
    assert score.total_score >= 70
    assert "Educational research" in score.disclaimer
    assert "growth" in score.component_scores
    assert score.target_allocation == "4-6%"


def test_overvalued_stock_is_flagged_even_with_bullish_trend():
    score = score_stock(_good_stock(pe=62, sector_pe=30))

    assert score.recommendation in {InvestmentRecommendation.WATCHLIST, InvestmentRecommendation.AVOID}
    assert any("Valuation is stretched" in risk for risk in score.risks)
    assert "overvalued" in score.reason


def test_high_debt_stock_is_avoided_when_cash_flow_is_weak():
    score = score_stock(_good_stock(debt_to_equity=2.1, operating_cash_flow_positive=False, free_cash_flow_positive=False))

    assert score.recommendation == InvestmentRecommendation.AVOID
    assert score.risk_level == "HIGH"
    assert any("High debt" in risk for risk in score.risks)
    assert any("Weak cash flow" in risk for risk in score.risks)


def test_good_mutual_fund_scores_buy_against_category_average():
    score = score_mutual_fund(_good_fund())

    assert score.recommendation == InvestmentRecommendation.BUY
    assert score.total_score >= 78
    assert score.category_comparison == "outperforming category average"
    assert "expense" in score.reason


def test_high_expense_mutual_fund_is_avoided():
    score = score_mutual_fund(_good_fund(expense_ratio=2.2))

    assert score.recommendation == InvestmentRecommendation.AVOID
    assert any("Expense ratio is high" in risk for risk in score.risks)


def test_poor_risk_adjusted_fund_is_avoided():
    score = score_mutual_fund(_good_fund(sharpe=0.35, sortino=0.5, beta=1.35, downside_capture=125))

    assert score.recommendation == InvestmentRecommendation.AVOID
    assert score.risk_level == "HIGH"
    assert any("Risk-adjusted return is weak" in risk for risk in score.risks)


def test_investing_dashboard_endpoint_returns_cards(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/investing/dashboard", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "Educational research" in payload["disclaimer"]
    assert "top_stock_picks" in payload["cards"]
    assert "top_mutual_funds" in payload["cards"]
    assert payload["summary"]
