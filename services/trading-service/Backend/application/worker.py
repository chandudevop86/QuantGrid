from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import time

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable


from Backend.application.broker_reconciliation import reconcile_broker_state

from Backend.application.fno_narrative_service import (
    run_fno_narrative
)

from Backend.application.investment_research_service import (
    latest_investment_dashboard,
    run_mutual_fund_research_loop,
    run_stock_research_loop,
)

from Backend.application.job_queue import (
    dequeue_job,
    mark_job_completed,
    mark_job_failed,
)

from Backend.application.job_store import (
    claim_job
)

from Backend.application.live_analysis_worker import (
    LiveAnalysisPayload,
    run_live_analysis,
)

from Backend.application.notifications import (
    send_alert
)

from Backend.application.redis_service import (
    redis_service
)

from Backend.application.trade_exit_engine import (
    monitor_open_positions
)

from Backend.core.database import (
    SessionLocal,
    init_database
)

from Backend.infrastructure.broker.broker_client import (
    broker_client_for_mode
)

from app.narratives.fo_narrative_loop import (
    is_market_hours_ist
)

from app.security.security_ops_loop import (
    SecurityCheckInput,
    run_security_scan
)


# NEW IMPORTS FOR CANDLE STORAGE

from Backend.application.market_data_service import (
    get_market_data_service
)
from Backend.domain.market_data.provider import MarketDataProviderError
from Backend.application.candle_validation import get_market_session, normalize_timestamp, validation_settings

from Backend.application.market_data_store import (
    store_candles
)

from Backend.application.notification_retry import NotificationRetryWorker



AUTO_SCAN_STRATEGIES = [
    "amd",
    "breakout",
    "btst",
    "cbt",
    "crt_tbs",
    "mean_reversion",
    "mtf",
    "mtfa",
    "supply_demand",
]


logger = logging.getLogger(__name__)


WORKER_ID = socket.gethostname()


_LAST_STOCK_RESEARCH_DATE: str | None = None
_LAST_FUND_RESEARCH_WEEK: str | None = None
_LAST_AUTO_PAPER_CANDLE: dict[str, str] = {}



# =====================================================
# ENV HELPERS
# =====================================================



def _truthy(value: str | None) -> bool:

    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }



def _not_falsey(
    value: str | None,
    *,
    default: bool
) -> bool:

    if value is None:
        return default

    return str(value).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }



def _float_env(
    name: str,
    default: float
) -> float:

    try:
        return float(
            os.getenv(
                name,
                default
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return default



# =====================================================
# CANDLE INGESTION CONFIG
# =====================================================


def _candle_ingestion_enabled() -> bool:

    return _not_falsey(
        os.getenv(
            "QUANTGRID_CANDLE_INGESTION_ENABLED"
        ),
        default=True,
    )



def _candle_ingestion_interval() -> float:

    return max(
        10.0,
        _float_env(
            "QUANTGRID_CANDLE_INGESTION_INTERVAL_SECONDS",
            60.0,
        ),
    )



def _candle_symbols() -> list[str]:

    configured = os.getenv(
        "QUANTGRID_CANDLE_SYMBOLS",
        "NIFTY",
    )

    return [
        item.strip().upper()
        for item in configured.split(",")
        if item.strip()
    ]



def _candle_interval() -> str:

    return os.getenv(
        "QUANTGRID_CANDLE_INTERVAL",
        "1m",
    )


def _candle_history_period() -> str:
    # Multi-day lookback also works when the current session has no candles.
    return os.getenv("QUANTGRID_CANDLE_HISTORY_PERIOD", "5d").strip() or "5d"


def _candle_history_limit() -> int:
    # Five 1-minute NSE sessions can exceed the previous 200-candle cap.
    return max(1, min(5000, int(_float_env("QUANTGRID_CANDLE_HISTORY_LIMIT", 2000))))


def _candle_market_hours_only() -> bool:
    """Keep periodic NSE ingestion within the normal weekday session by default.

    Set QUANTGRID_CANDLE_MARKET_HOURS_ONLY=false for explicit backfill or
    instruments using other sessions. The calendar helper does not track
    exchange-specific holidays.
    """
    return _not_falsey(
        os.getenv("QUANTGRID_CANDLE_MARKET_HOURS_ONLY"),
        default=True,
    )



# =====================================================
# CANDLE FETCH + DATABASE STORAGE
# =====================================================


def _run_candle_ingestion():

    if _candle_market_hours_only() and not is_market_hours_ist():
        logger.debug("candle_ingestion_skipped reason=outside_market_hours")
        return

    service = get_market_data_service()

    symbols = _candle_symbols()

    interval = _candle_interval()


    for symbol in symbols:

        try:
            response = service.get_candles(
                symbol,
                interval=interval,
                period=_candle_history_period(),
                limit=_candle_history_limit(),
            )
        except MarketDataProviderError as exc:
            logger.warning(
                "candle_ingestion_provider_error symbol=%s interval=%s error=%s",
                symbol,
                interval,
                exc,
            )
            continue


        candles = response.get(
            "candles",
            []
        )


        if not candles:

            logger.warning(
                "candle_ingestion_empty symbol=%s source=%s",
                symbol,
                response.get("source"),
            )

            continue



        store_candles(
            symbol=symbol,
            market_symbol=response.get(
                "market_symbol"
            ),
            interval=interval,
            source=response.get(
                "source"
            ),
            candles=candles,
        )


        logger.info(
            "candle_ingestion_completed symbol=%s interval=%s candles=%s source=%s",
            symbol,
            interval,
            len(candles),
            response.get("source"),
        )
        
        
        # =====================================================
# JOB EXECUTION HANDLERS
# =====================================================


def _job_type(
    job: dict[str, Any],
    payload: dict[str, Any]
) -> str:

    return str(
        job.get("job_type")
        or payload.get("job_type")
        or "live-analysis"
    )



def _run_live_analysis_job(
    payload: dict[str, Any]
) -> dict[str, Any]:

    return run_live_analysis(
        LiveAnalysisPayload(**payload)
    )



def _run_auto_paper_job(
    payload: dict[str, Any]
) -> dict[str, Any]:

    raw_strategies = payload.get(
        "strategies"
    )


    if isinstance(
        raw_strategies,
        list
    ) and raw_strategies:

        strategies = [
            str(item)
            for item in raw_strategies
        ]

    else:

        strategies = list(
            AUTO_SCAN_STRATEGIES
        )



    results: dict[str, Any] = {}


    for strategy_name in strategies:

        live_payload = LiveAnalysisPayload(

            symbol=str(
                payload.get("symbol")
                or "NIFTY"
            ),

            interval=str(
                payload.get("interval")
                or "1m"
            ),

            period=str(
                payload.get("period")
                or "1d"
            ),

            strategy=strategy_name,


            capital=float(
                payload.get("capital")
                or 100000
            ),


            risk_pct=float(
                payload.get("risk_pct")
                or 1
            ),


            rr_ratio=float(
                payload.get("rr_ratio")
                or 2
            ),


            auto_trade=True,

            execution_mode="paper",
        )



        try:

            results[strategy_name] = (
                run_live_analysis(
                    live_payload
                )
            )


        except Exception as exc:

            results[strategy_name] = {
                "error": str(exc)
            }



    if len(strategies) == 1:

        return results[strategies[0]]


    return {
        "strategies": results
    }



# =====================================================
# BROKER RECONCILIATION
# =====================================================


async def _run_reconciliation_job_async(
    payload: dict[str, Any]
) -> dict[str, Any]:

    execution_mode = str(
        payload.get(
            "execution_mode"
        )
        or "paper"
    ).lower()


    actor = SimpleNamespace(
        id=None,
        username="worker",
        role="ops",
    )


    with SessionLocal() as db:

        return await reconcile_broker_state(
            db=db,
            broker_client=
                broker_client_for_mode(
                    execution_mode
                ),
            actor=actor,
            execution_mode=execution_mode,
            request=None,
        )



def _run_reconciliation_job(
    payload: dict[str, Any]
):

    return asyncio.run(
        _run_reconciliation_job_async(
            payload
        )
    )



# =====================================================
# EXIT MONITOR
# =====================================================


async def _run_exit_monitor_job_async(
    payload: dict[str, Any]
):

    execution_mode = str(
        payload.get(
            "execution_mode"
        )
        or "paper"
    ).lower()



    actor = SimpleNamespace(
        id=None,
        username="worker",
        role="ops",
    )



    with SessionLocal() as db:

        return await monitor_open_positions(
            db=db,
            actor=actor,
            request=None,
            execution_mode=execution_mode,
            broker_client=
                broker_client_for_mode(
                    execution_mode
                ),
        )



def _run_exit_monitor_job(
    payload: dict[str, Any]
):

    return asyncio.run(
        _run_exit_monitor_job_async(
            payload
        )
    )



# =====================================================
# NOTIFICATION
# =====================================================


def _run_notification_job(
    payload: dict[str, Any]
):

    subject = str(
        payload.get(
            "subject"
        )
        or "QuantGrid notification"
    )


    message = str(
        payload.get("message")
        or payload.get("body")
        or ""
    )


    send_alert(
        subject,
        message
    )


    return {
        "status": "sent",
        "subject": subject,
    }

async def _run_notification_retry_job_async(
    payload: dict[str, Any]
) -> dict[str, Any]:

    with SessionLocal() as db:
        worker = NotificationRetryWorker(db)
        return await worker.run()


def _run_notification_retry_job(
    payload: dict[str, Any]
) -> dict[str, Any]:

    return asyncio.run(
        _run_notification_retry_job_async(payload)
    )
    

def _notification_retry_enabled() -> bool:
    return _not_falsey(
        os.getenv(
            "QUANTGRID_NOTIFICATION_RETRY_ENABLED"
        ),
        default=True,
    )


def _notification_retry_interval() -> float:
    return max(
        30.0,
        _float_env(
            "QUANTGRID_NOTIFICATION_RETRY_INTERVAL_SECONDS",
            60.0,
        ),
    )


def _run_periodic_notification_retry():
    return _run_notification_retry_job({})



# =====================================================
# FNO NARRATIVE
# =====================================================


def _run_fno_narrative_job(
    payload: dict[str, Any]
):

    symbol = str(
        payload.get("symbol")
        or "NIFTY"
    ).upper()



    result = run_fno_narrative(
        symbol
    )


    if hasattr(
        result,
        "model_dump"
    ):

        return result.model_dump()


    return result.dict()



# =====================================================
# INVESTMENT RESEARCH
# =====================================================


def _run_investment_research_job(
    payload: dict[str, Any]
):

    scope = str(
        payload.get(
            "scope"
        )
        or "dashboard"
    ).lower()



    if scope == "stocks":

        scores = (
            run_stock_research_loop(
                persist=True
            )
        )


        return {
            "status": "completed",
            "scope": "stocks",
            "items": [
                item.model_dump()
                for item in scores
            ],
        }



    if scope in {
        "mutual_funds",
        "funds"
    }:

        scores = (
            run_mutual_fund_research_loop(
                persist=True
            )
        )


        return {
            "status": "completed",
            "scope": "mutual_funds",
            "items": [
                item.model_dump()
                for item in scores
            ],
        }



    return {
        "status": "completed",
        "scope": scope,
        "dashboard":
            latest_investment_dashboard(),
    }



# =====================================================
# SECURITY SCAN
# =====================================================


def _run_security_scan_job(
    payload: dict[str, Any]
):

    scan_type = str(
        payload.get(
            "scan_type"
        )
        or "full"
    ).lower()



    result = run_security_scan(
        SecurityCheckInput(
            scan_type=scan_type
        ),
        persist=True,
    )


    if hasattr(
        result,
        "model_dump"
    ):

        return result.model_dump(
            mode="json"
        )


    return result.dict()



# =====================================================
# JOB HANDLER MAP
# =====================================================

HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "live-analysis": _run_live_analysis_job,
    "auto-paper": _run_auto_paper_job,
    "order-reconciliation": _run_reconciliation_job,
    "exit-monitor": _run_exit_monitor_job,
    "notification": _run_notification_job,

    # NEW
    "notification-retry": _run_notification_retry_job,

    "fno-narrative": _run_fno_narrative_job,
    "investment-research": _run_investment_research_job,
    "security-scan": _run_security_scan_job,
}    

# =====================================================
# JOB PROCESSING
# =====================================================


def _process_claimed_job(
    claimed: tuple[dict[str, Any], dict[str, Any]]
) -> dict[str, Any] | None:

    job, payload = claimed

    job_id = str(
        job["job_id"]
    )

    job_type = _job_type(
        job,
        payload
    )


    handler = HANDLERS.get(
        job_type
    )


    if handler is None:

        return mark_job_failed(
            job_id,
            f"Unsupported job type: {job_type}"
        )


    try:

        logger.info(
            "Worker processing %s job %s",
            job_type,
            job_id,
        )


        result = handler(
            payload
        )


        return mark_job_completed(
            job_id,
            result
        )


    except Exception as exc:

        logger.exception(
            "Worker failed %s job %s",
            job_type,
            job_id,
        )


        return mark_job_failed(
            job_id,
            str(exc)
        )



def process_next_job():

    claimed = dequeue_job()

    if claimed is None:

        return None


    return _process_claimed_job(
        claimed
    )



def process_job(
    job_id: str
):

    claimed = claim_job(
        job_id
    )


    if claimed is None:

        return None


    return _process_claimed_job(
        claimed
    )



# =====================================================
# PERIODIC TASK HELPERS
# =====================================================


def _paper_reconciliation_enabled() -> bool:
    """Enable periodic reconciliation for PAPER execution only."""
    return _truthy(
        os.getenv(
            "QUANTGRID_PAPER_RECONCILIATION_ENABLED",
            "true",
        )
    )


def _paper_reconciliation_interval() -> float:
    return max(
        5.0,
        _float_env(
            "QUANTGRID_PAPER_RECONCILIATION_INTERVAL_SECONDS",
            30.0,
        ),
    )


def _run_periodic_paper_reconciliation() -> dict[str, Any]:
    # Intentionally hard-coded. Periodic reconciliation introduced for the
    # automated paper lifecycle must never inherit or switch to live mode.
    return _run_reconciliation_job(
        {"execution_mode": "paper"}
    )


def _exit_monitor_enabled():

    return _truthy(
        os.getenv(
            "QUANTGRID_EXIT_MONITOR_ENABLED"
        )
    )



def _exit_monitor_interval():

    return max(
        1.0,
        _float_env(
            "QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS",
            5,
        )
    )



def _exit_monitor_mode():

    mode = str(
        os.getenv(
            "QUANTGRID_EXIT_MONITOR_MODE",
            "paper",
        )
    ).strip().lower()

    if mode not in {"paper", "live"}:
        return "paper"

    return mode



def _run_periodic_exit_monitor():

    payload = {
        "execution_mode": _exit_monitor_mode()
    }

    return _run_exit_monitor_job(
        payload
    )



def _auto_paper_enabled() -> bool:
    return _truthy(
        os.getenv(
            "QUANTGRID_AUTO_PAPER_ENABLED"
        )
    )


def _auto_paper_interval() -> float:
    return max(
        30.0,
        _float_env(
            "QUANTGRID_AUTO_PAPER_INTERVAL_SECONDS",
            60.0,
        ),
    )


def _auto_paper_symbols() -> list[str]:
    configured = os.getenv(
        "QUANTGRID_AUTO_PAPER_SYMBOLS",
        "NIFTY",
    )
    symbols = [
        item.strip().upper()
        for item in configured.split(",")
        if item.strip()
    ]
    return symbols or ["NIFTY"]


def _run_periodic_auto_paper() -> dict[str, Any]:
    # The weekday/time-only narrative helper does not check NSE holidays.
    if not get_market_session().market_live:
        return {"status": "outside_market_hours", "execution_mode": "paper"}

    service = get_market_data_service()
    results: dict[str, Any] = {}

    for symbol in _auto_paper_symbols():
        response = service.get_candles(
            symbol,
            interval="1m",
            period="1d",
            limit=2,
        )
        candles = list(response.get("candles") or [])
        if not candles:
            results[symbol] = {"status": "no_market_data"}
            continue

        latest_candle = str(candles[-1].get("timestamp") or "")
        if not latest_candle:
            results[symbol] = {"status": "missing_candle_timestamp"}
            continue

        # Historical/paper-analysis freshness does not imply trade eligibility.
        # Fail closed on missing, future or delayed timestamps even if the
        # response describes old holiday candles as fresh for analysis.
        latest_at = normalize_timestamp(latest_candle)
        now = datetime.now(timezone.utc).astimezone(latest_at.tzinfo) if latest_at else None
        max_age = validation_settings().reject_after_seconds
        if latest_at is None or now is None or not (0 <= (now - latest_at).total_seconds() <= max_age):
            results[symbol] = {"status": "stale_candle", "latest_candle": latest_candle}
            continue

        if _LAST_AUTO_PAPER_CANDLE.get(symbol) == latest_candle:
            results[symbol] = {
                "status": "already_scanned",
                "latest_candle": latest_candle,
            }
            continue

        _LAST_AUTO_PAPER_CANDLE[symbol] = latest_candle
        results[symbol] = _run_auto_paper_job(
            {
                "symbol": symbol,
                "interval": "1m",
                "period": "1d",
                "capital": 100000,
                "risk_pct": 1,
                "rr_ratio": 2,
            }
        )

    return {
        "status": "completed",
        "execution_mode": "paper",
        "symbols": results,
    }


def _narrative_loop_enabled():

    return _not_falsey(
        os.getenv(
            "QUANTGRID_FNO_NARRATIVE_LOOP_ENABLED"
        ),
        default=True,
    )



def _narrative_loop_interval():

    return max(
        60,
        _float_env(
            "QUANTGRID_FNO_NARRATIVE_INTERVAL_SECONDS",
            300,
        )
    )



def _narrative_symbols():

    configured = os.getenv(
        "QUANTGRID_FNO_NARRATIVE_SYMBOLS",
        "NIFTY,BANKNIFTY",
    )

    symbols = [
        symbol.strip().upper()
        for symbol in configured.split(",")
        if symbol.strip()
    ]

    return symbols or ["NIFTY", "BANKNIFTY"]




def _investment_loop_enabled():

    return _not_falsey(
        os.getenv(
            "QUANTGRID_INVESTMENT_RESEARCH_LOOP_ENABLED"
        ),
        default=True,
    )


def _investment_loop_interval():

    return max(
        300.0,
        _float_env(
            "QUANTGRID_INVESTMENT_RESEARCH_CHECK_SECONDS",
            300,
        )
    )


def _run_periodic_fno_narratives():

    if not is_market_hours_ist():

        return {
            "status":
                "outside_market_hours"
        }


    for symbol in _narrative_symbols():

        run_fno_narrative(
            symbol
        )


    return {
        "status":
            "completed"
    }



# =====================================================
# MAIN WORKER LOOP
# =====================================================


def run_worker_loop(
    poll_interval: float = 1.0
):

    init_database()

    redis_service.configure()


    logger.info(
        "QuantGrid worker started id=%s",
        WORKER_ID
    )


    next_heartbeat = time.monotonic()

    next_candle_ingestion = time.monotonic()

    next_exit_check = time.monotonic()
    next_paper_reconciliation = time.monotonic()

    next_auto_paper_check = time.monotonic()

    next_narrative_check = time.monotonic()
    
    next_notification_retry = time.monotonic()

    while True:


        # -------------------------
        # heartbeat
        # -------------------------

        if time.monotonic() >= next_heartbeat:

            redis_service.write_worker_heartbeat(
                {
                    "worker_id":
                        WORKER_ID,

                    "status":
                        "RUNNING",

                    "last_seen":
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                },

                ttl_seconds=15,
            )


            next_heartbeat = (
                time.monotonic()
                + 5
            )



        # -------------------------
        # candle ingestion
        # -------------------------

        if (
            _candle_ingestion_enabled()
            and
            time.monotonic()
            >= next_candle_ingestion
        ):

            try:

                _run_candle_ingestion()


            except Exception:

                logger.exception(
                    "Candle ingestion failed"
                )


            next_candle_ingestion = (
                time.monotonic()
                +
                _candle_ingestion_interval()
            )



        # -------------------------
        # queued jobs
        # -------------------------

        process_next_job()
        
        if (
            _notification_retry_enabled()
            and
            time.monotonic() >= next_notification_retry
        ):
            try:
                _run_periodic_notification_retry()
            except Exception:
                logger.exception("Notification retry failed")

            next_notification_retry = (
                time.monotonic()
                + _notification_retry_interval()
            )


        # -------------------------
        # automatic paper scan
        # -------------------------

        if (
            _auto_paper_enabled()
            and
            time.monotonic() >= next_auto_paper_check
        ):
            try:
                result = _run_periodic_auto_paper()
                logger.info("auto_paper_periodic_scan result=%s", result.get("status"))
            except Exception:
                logger.exception("Automatic paper scan failed")

            next_auto_paper_check = (
                time.monotonic()
                + _auto_paper_interval()
            )


        # -------------------------
        # periodic PAPER reconciliation
        # -------------------------
        if (
            _paper_reconciliation_enabled()
            and
            time.monotonic()
            >= next_paper_reconciliation
        ):
            try:
                result = _run_periodic_paper_reconciliation()
                logger.info(
                    "paper_reconciliation_periodic result=%s",
                    result,
                )
            except Exception:
                logger.exception(
                    "Periodic PAPER reconciliation failed"
                )

            next_paper_reconciliation = (
                time.monotonic()
                + _paper_reconciliation_interval()
            )

        # -------------------------
        # exit monitor
        # -------------------------

        if (
            _exit_monitor_enabled()
            and
            time.monotonic()
            >= next_exit_check
        ):

            try:

                _run_periodic_exit_monitor()

            except Exception:

                logger.exception(
                    "Exit monitor failed"
                )


            next_exit_check = (
                time.monotonic()
                +
                _exit_monitor_interval()
            )



        # -------------------------
        # FNO loop
        # -------------------------

        if (
            _narrative_loop_enabled()
            and
            time.monotonic()
            >= next_narrative_check
        ):

            try:

                _run_periodic_fno_narratives()


            except Exception:

                logger.exception(
                    "FNO narrative failed"
                )


            next_narrative_check = (
                time.monotonic()
                +
                _narrative_loop_interval()
            )



        time.sleep(
            poll_interval
        )



# =====================================================
# ENTRY POINT
# =====================================================


def main():

    parser = argparse.ArgumentParser(
        description=
        "Run QuantGrid worker"
    )


    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0
    )


    parser.add_argument(
        "--once",
        action="store_true"
    )


    args = parser.parse_args()


    logging.basicConfig(
        level=logging.INFO
    )


    if args.once:

        process_next_job()

        return



    try:
        run_worker_loop(
            poll_interval=args.poll_interval
        )
    except KeyboardInterrupt:
        logger.info("QuantGrid worker stopped on SIGINT")


if __name__ == "__main__":

    main()