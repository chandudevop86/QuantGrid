from __future__ import annotations

import json
import os
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from Backend.core.database import SessionLocal, init_database
from Backend.domain.trading_store_models import InvestmentResearchRecord
from app.investing.investment_research_loop import (
    DISCLAIMER,
    MutualFundInput,
    MutualFundScore,
    StockResearchInput,
    StockScore,
    build_investment_dashboard,
    score_mutual_fund,
    score_stock,
)

IST = ZoneInfo("Asia/Kolkata")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_symbols(env_name: str, default: str) -> list[str]:
    configured = os.getenv(env_name, default)
    return [item.strip().upper() for item in configured.split(",") if item.strip()]


def sample_stock_universe() -> list[StockResearchInput]:
    names = {
        "TCS": ("Tata Consultancy Services", "IT"),
        "INFY": ("Infosys", "IT"),
        "RELIANCE": ("Reliance Industries", "Energy"),
        "HDFCBANK": ("HDFC Bank", "Financials"),
        "LT": ("Larsen & Toubro", "Industrials"),
    }
    universe: list[StockResearchInput] = []
    for symbol in _parse_symbols("QUANTGRID_INVESTING_STOCKS", "TCS,INFY,RELIANCE,HDFCBANK,LT"):
        name, sector = names.get(symbol, (symbol, "Diversified"))
        universe.append(
            StockResearchInput(
                symbol=symbol,
                name=name,
                sector=sector,
                revenue_growth_3y=13 if symbol != "RELIANCE" else 9,
                profit_growth_3y=14 if symbol != "RELIANCE" else 8,
                quarterly_revenue_growth=10,
                quarterly_profit_growth=11,
                debt_to_equity=0.2 if symbol in {"TCS", "INFY"} else 0.8,
                operating_cash_flow_positive=True,
                free_cash_flow_positive=symbol != "RELIANCE",
                roe=25 if symbol in {"TCS", "INFY", "HDFCBANK"} else 15,
                roce=30 if symbol in {"TCS", "INFY"} else 16,
                promoter_holding=55,
                fii_holding_change=0.5,
                dii_holding_change=0.4,
                pe=28 if symbol in {"TCS", "INFY"} else 32,
                sector_pe=30,
                pb=6 if symbol in {"TCS", "INFY"} else 4,
                eps_growth=13,
                dividend_years=8,
                sector_trend="positive" if sector in {"IT", "Financials"} else "neutral",
                price_trend="uptrend",
                price_to_52w_high_pct=10,
                price_above_200dma=True,
                news_sentiment="neutral",
            )
        )
    return universe


def sample_mutual_fund_universe() -> list[MutualFundInput]:
    return [
        MutualFundInput(
            scheme_code="QG-LARGE-MID",
            name="QuantGrid Large & Midcap Quality Fund",
            category="Large & Mid Cap",
            nav=125.4,
            aum_cr=8200,
            aum_growth_pct=12,
            expense_ratio=0.72,
            return_1y=18,
            return_3y=17,
            return_5y=16,
            category_return_1y=15,
            category_return_3y=14,
            category_return_5y=13,
            alpha=3.2,
            beta=0.95,
            sharpe=1.35,
            sortino=1.75,
            fund_manager_years=6,
            downside_capture=82,
            category_rank_percentile=12,
            return_consistency_years=5,
        ),
        MutualFundInput(
            scheme_code="QG-FLEXI",
            name="QuantGrid Flexicap Compounder Fund",
            category="Flexi Cap",
            nav=88.2,
            aum_cr=5400,
            aum_growth_pct=8,
            expense_ratio=0.92,
            return_1y=14,
            return_3y=15,
            return_5y=14,
            category_return_1y=13,
            category_return_3y=13,
            category_return_5y=12,
            alpha=2.1,
            beta=1.02,
            sharpe=1.08,
            sortino=1.36,
            fund_manager_years=4,
            downside_capture=92,
            category_rank_percentile=28,
            return_consistency_years=4,
        ),
    ]


def init_investment_research_store() -> None:
    init_database()


def _score_to_record(score: StockScore | MutualFundScore) -> InvestmentResearchRecord:
    if isinstance(score, StockScore):
        identifier = score.symbol
        asset_type = "stock"
    else:
        identifier = score.scheme_code
        asset_type = "mutual_fund"
    return InvestmentResearchRecord(
        asset_type=asset_type,
        identifier=identifier,
        name=score.name,
        score=score.total_score,
        recommendation=score.recommendation.value,
        risk_level=score.risk_level,
        scored_at=score.scored_at or _utc_now(),
        payload_json=json.dumps(score.model_dump(), default=str),
    )


def store_research_scores(scores: list[StockScore | MutualFundScore], db: Session | None = None) -> None:
    init_investment_research_store()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        for score in scores:
            session.add(_score_to_record(score))
        session.commit()
    finally:
        if owns_session:
            session.close()


def _latest_records(asset_type: str, limit: int = 50, db: Session | None = None) -> list[dict[str, Any]]:
    init_investment_research_store()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        rows = (
            session.query(InvestmentResearchRecord)
            .filter(InvestmentResearchRecord.asset_type == asset_type)
            .order_by(InvestmentResearchRecord.scored_at.desc(), InvestmentResearchRecord.score.desc())
            .limit(limit * 4)
            .all()
        )
        latest: dict[str, InvestmentResearchRecord] = {}
        for row in rows:
            latest.setdefault(row.identifier, row)
            if len(latest) >= limit:
                break
        return [json.loads(row.payload_json) for row in latest.values()]
    finally:
        if owns_session:
            session.close()


def latest_stock_research(limit: int = 50, db: Session | None = None) -> list[dict[str, Any]]:
    records = _latest_records("stock", limit=limit, db=db)
    if records:
        return records
    scores = run_stock_research_loop(persist=True)
    return [score.model_dump() for score in scores[:limit]]


def latest_mutual_fund_research(limit: int = 50, db: Session | None = None) -> list[dict[str, Any]]:
    records = _latest_records("mutual_fund", limit=limit, db=db)
    if records:
        return records
    scores = run_mutual_fund_research_loop(persist=True)
    return [score.model_dump() for score in scores[:limit]]


def run_stock_research_loop(
    inputs: list[StockResearchInput] | None = None,
    *,
    persist: bool = True,
    db: Session | None = None,
) -> list[StockScore]:
    scores = [score_stock(item) for item in (inputs or sample_stock_universe())]
    scores.sort(key=lambda item: item.total_score, reverse=True)
    if persist:
        store_research_scores(scores, db=db)
    return scores


def run_mutual_fund_research_loop(
    inputs: list[MutualFundInput] | None = None,
    *,
    persist: bool = True,
    db: Session | None = None,
) -> list[MutualFundScore]:
    scores = [score_mutual_fund(item) for item in (inputs or sample_mutual_fund_universe())]
    scores.sort(key=lambda item: item.total_score, reverse=True)
    if persist:
        store_research_scores(scores, db=db)
    return scores


def run_portfolio_watchlist_loop(
    stocks: list[StockResearchInput] | None = None,
    funds: list[MutualFundInput] | None = None,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    stock_scores = run_stock_research_loop(stocks, persist=persist)
    fund_scores = run_mutual_fund_research_loop(funds, persist=persist)
    return investment_dashboard_from_scores(stock_scores, fund_scores)


def investment_dashboard_from_scores(
    stock_scores: list[StockScore],
    fund_scores: list[MutualFundScore],
) -> dict[str, Any]:
    dashboard = build_investment_dashboard(stock_scores, fund_scores)
    return {
        "generated_at": _utc_now(),
        "summary": dashboard["summary"],
        "cards": dashboard["cards"],
        "stocks": [item.model_dump() for item in stock_scores],
        "mutual_funds": [item.model_dump() for item in fund_scores],
        "disclaimer": DISCLAIMER,
    }


def latest_investment_dashboard(db: Session | None = None) -> dict[str, Any]:
    stock_scores = [StockScore(**item) for item in latest_stock_research(db=db)]
    fund_scores = [MutualFundScore(**item) for item in latest_mutual_fund_research(db=db)]
    return investment_dashboard_from_scores(stock_scores, fund_scores)


def is_after_market_close_ist(now: datetime | None = None) -> bool:
    current = (now or datetime.now(timezone.utc)).astimezone(IST)
    return current.weekday() < 5 and current.time() >= time(15, 45)


def is_weekend_ist(now: datetime | None = None) -> bool:
    current = (now or datetime.now(timezone.utc)).astimezone(IST)
    return current.weekday() >= 5
