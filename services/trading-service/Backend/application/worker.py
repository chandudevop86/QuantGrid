from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import time
from types import SimpleNamespace
from typing import Any, Callable

from Backend.application.broker_reconciliation import reconcile_broker_state
from Backend.application.job_queue import dequeue_job, mark_job_completed, mark_job_failed
from Backend.application.live_analysis_worker import LiveAnalysisPayload, run_live_analysis
from Backend.application.notifications import send_alert
from Backend.application.trade_exit_engine import monitor_open_positions
from Backend.core.database import SessionLocal, init_database
from Backend.infrastructure.broker.broker_client import broker_client_for_mode

logger = logging.getLogger(__name__)
WORKER_ID = socket.gethostname()


def _job_type(job: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(job.get("job_type") or payload.get("job_type") or "live-analysis")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _exit_monitor_enabled() -> bool:
    return _truthy(os.getenv("QUANTGRID_EXIT_MONITOR_ENABLED"))


def _exit_monitor_interval() -> float:
    return max(1.0, _float_env("QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS", 5.0))


def _exit_monitor_mode() -> str:
    mode = str(os.getenv("QUANTGRID_EXIT_MONITOR_MODE") or "paper").strip().lower()
    return mode if mode in {"paper", "live"} else "paper"


def _run_live_analysis_job(payload: dict[str, Any]) -> dict[str, Any]:
    return run_live_analysis(LiveAnalysisPayload(**payload))


def _run_auto_paper_job(payload: dict[str, Any]) -> dict[str, Any]:
    live_payload = LiveAnalysisPayload(
        symbol=str(payload.get("symbol") or "NIFTY"),
        interval=str(payload.get("interval") or "1m"),
        period=str(payload.get("period") or "1d"),
        strategy=str((payload.get("strategies") or ["breakout"])[0] if isinstance(payload.get("strategies"), list) else payload.get("strategy") or "breakout"),
        capital=float(payload.get("capital") or 100000),
        risk_pct=float(payload.get("risk_pct") or 1),
        rr_ratio=float(payload.get("rr_ratio") or 2),
        auto_trade=True,
        execution_mode="paper",
    )
    return run_live_analysis(live_payload)


async def _run_reconciliation_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    execution_mode = str(payload.get("execution_mode") or "paper").strip().lower()
    actor = SimpleNamespace(id=None, username="worker", role="ops")
    with SessionLocal() as db:
        return await reconcile_broker_state(
            db=db,
            broker_client=broker_client_for_mode(execution_mode),
            actor=actor,  # type: ignore[arg-type]
            request=None,
        )


def _run_reconciliation_job(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_run_reconciliation_job_async(payload))


async def _run_exit_monitor_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    execution_mode = str(payload.get("execution_mode") or "paper").strip().lower()
    actor = SimpleNamespace(id=None, username="worker", role="ops")
    with SessionLocal() as db:
        return await monitor_open_positions(
            db=db,
            actor=actor,  # type: ignore[arg-type]
            request=None,
            execution_mode=execution_mode,
            broker_client=broker_client_for_mode(execution_mode),
        )


def _run_exit_monitor_job(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_run_exit_monitor_job_async(payload))


def _run_notification_job(payload: dict[str, Any]) -> dict[str, str]:
    subject = str(payload.get("subject") or "QuantGrid notification")
    message = str(payload.get("message") or payload.get("body") or "")
    send_alert(subject, message)
    return {"status": "sent", "subject": subject}


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "live-analysis": _run_live_analysis_job,
    "auto-paper": _run_auto_paper_job,
    "order-reconciliation": _run_reconciliation_job,
    "exit-monitor": _run_exit_monitor_job,
    "notification": _run_notification_job,
}


def process_next_job() -> dict[str, Any] | None:
    claimed = dequeue_job()
    if claimed is None:
        return None

    job, payload = claimed
    job_id = str(job["job_id"])
    job_type = _job_type(job, payload)
    handler = HANDLERS.get(job_type)
    if handler is None:
        return mark_job_failed(job_id, f"Unsupported job type: {job_type}")

    try:
        logger.info("Worker processing %s job %s", job_type, job_id)
        result = handler(payload)
        return mark_job_completed(job_id, result)
    except Exception as exc:
        logger.exception("Worker failed %s job %s", job_type, job_id)
        return mark_job_failed(job_id, str(exc))


def _run_periodic_exit_monitor() -> dict[str, Any]:
    payload = {"execution_mode": _exit_monitor_mode()}
    logger.info("Worker running periodic exit monitor in %s mode", payload["execution_mode"])
    return _run_exit_monitor_job(payload)


def run_worker_loop(poll_interval: float = 1.0) -> None:
    init_database()
    logger.info("QuantGrid worker started with id %s", WORKER_ID)
    next_exit_check = time.monotonic()
    while True:
        processed = process_next_job()
        if _exit_monitor_enabled() and time.monotonic() >= next_exit_check:
            try:
                _run_periodic_exit_monitor()
            except Exception:
                logger.exception("Periodic exit monitor failed")
            next_exit_check = time.monotonic() + _exit_monitor_interval()
        if processed is None:
            time.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the QuantGrid background worker.")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true", help="Process at most one queued job and exit.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    init_database()
    if args.once:
        process_next_job()
        return
    run_worker_loop(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
