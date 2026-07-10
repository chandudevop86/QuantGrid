from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from Backend.application.backtest_job_store import (
    claim_recoverable_backtest_jobs,
    clear_backtest_jobs_for_tests,
    create_backtest_job,
    get_backtest_job_record,
    list_backtest_job_records,
    update_backtest_job_record,
)
from Backend.application.quant_modules import backtesting_module


BACKTEST_STATES = {"QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"}
DEFAULT_STRATEGIES = ["amd", "breakout", "btst", "cbt", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"]
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="quantgrid-backtest")
_LOCK = threading.RLock()
_JOBS: dict[str, "BacktestJob"] = {}
_RECOVERED = False
_WORKER_ID = f"backtest-worker-{uuid.uuid4()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BacktestJob:
    job_id: str
    payload: dict[str, Any]
    strategies: list[str]
    status: str = "QUEUED"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    current_strategy: str | None = None
    completed_strategies: int = 0
    total_strategies: int = 0
    partial_results: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False
    expected_seconds: float = 45.0
    recovery_owner: str | None = None
    recovery_lease_until: str | None = None


def start_backtest_job(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_recovered_jobs()
    payload = payload or {}
    strategies = _normalize_strategies(payload.get("strategies"))
    job = BacktestJob(
        job_id=str(uuid.uuid4()),
        payload={key: value for key, value in payload.items() if key != "candles"} | ({"candles": payload.get("candles")} if payload.get("candles") else {}),
        strategies=strategies,
        total_strategies=len(strategies),
        expected_seconds=float(payload.get("expected_seconds") or 45.0),
    )
    with _LOCK:
        _JOBS[job.job_id] = job
        create_backtest_job(_job_to_record(job), job.payload)
        snapshot = _job_snapshot(job)
    _EXECUTOR.submit(_run_backtest_job, job.job_id)
    return snapshot


def get_backtest_job(job_id: str) -> dict[str, Any] | None:
    _ensure_recovered_jobs()
    with _LOCK:
        record = get_backtest_job_record(job_id)
        job = _job_from_record(record) if record else _JOBS.get(job_id)
        return _job_snapshot(job) if job else None


def cancel_backtest_job(job_id: str) -> dict[str, Any] | None:
    _ensure_recovered_jobs()
    with _LOCK:
        record = get_backtest_job_record(job_id)
        job = _JOBS.get(job_id) or (_job_from_record(record) if record else None)
        if job is None:
            return None
        job.cancel_requested = True
        if job.status in {"QUEUED", "RUNNING", "TIMEOUT"}:
            job.status = "CANCELLED"
            job.completed_at = _utc_now()
            job.updated_at = job.completed_at
        _JOBS[job.job_id] = job
        _persist_job(job)
        return _job_snapshot(job)


def list_backtest_jobs(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_recovered_jobs()
    records = list_backtest_job_records(limit=max(1, min(int(limit), 100)))
    return [_job_snapshot(_job_from_record(record)) for record in records]


def reset_backtest_jobs_for_tests() -> None:
    global _RECOVERED
    with _LOCK:
        _JOBS.clear()
        clear_backtest_jobs_for_tests()
        _RECOVERED = True


def _run_backtest_job(job_id: str) -> None:
    with _LOCK:
        record = get_backtest_job_record(job_id)
        job = _JOBS.get(job_id) or (_job_from_record(record) if record else None)
        if job is None or job.cancel_requested:
            return
        _JOBS[job.job_id] = job
        job.status = "RUNNING"
        job.started_at = job.started_at or _utc_now()
        job.completed_at = None
        job.updated_at = job.started_at
        _persist_job(job)

    try:
        completed = {str(run.get("strategy")) for run in job.partial_results}
        for strategy in [item for item in list(job.strategies) if item not in completed]:
            with _LOCK:
                record = get_backtest_job_record(job_id)
                current = _JOBS.get(job_id) or (_job_from_record(record) if record else None)
                if current is None or current.cancel_requested:
                    return
                _JOBS[current.job_id] = current
                current.current_strategy = strategy
                current.updated_at = _utc_now()
                _persist_job(current)

            result = backtesting_module(_strategy_payload(job.payload, strategy))
            metrics = result.get("metrics", {})
            run = {
                "strategy": strategy,
                "symbol": result.get("symbol"),
                "metrics": metrics,
                "cost_model": result.get("cost_model", {}),
                "equity_curve": result.get("equity_curve", []),
                "recent_outcomes": result.get("recent_outcomes", []),
            }
            with _LOCK:
                record = get_backtest_job_record(job_id)
                current = _JOBS.get(job_id) or (_job_from_record(record) if record else None)
                if current is None:
                    return
                _JOBS[current.job_id] = current
                current.partial_results.append(run)
                current.completed_strategies = len(current.partial_results)
                current.updated_at = _utc_now()
                if current.cancel_requested:
                    current.status = "CANCELLED"
                    current.completed_at = current.updated_at
                    _persist_job(current)
                    return
                if _elapsed_seconds(current) > current.expected_seconds:
                    current.status = "TIMEOUT"
                _persist_job(current)

        with _LOCK:
            record = get_backtest_job_record(job_id)
            current = _JOBS.get(job_id) or (_job_from_record(record) if record else None)
            if current is None:
                return
            _JOBS[current.job_id] = current
            current.result = _comparison_result(current)
            current.status = "CANCELLED" if current.cancel_requested else "COMPLETED"
            current.current_strategy = None
            current.completed_at = _utc_now()
            current.updated_at = current.completed_at
            _persist_job(current)
    except Exception as exc:
        with _LOCK:
            record = get_backtest_job_record(job_id)
            current = _JOBS.get(job_id) or (_job_from_record(record) if record else None)
            if current is None:
                return
            _JOBS[current.job_id] = current
            current.status = "FAILED"
            current.error = _friendly_error(exc)
            current.completed_at = _utc_now()
            current.updated_at = current.completed_at
            _persist_job(current)


def _ensure_recovered_jobs() -> None:
    global _RECOVERED
    with _LOCK:
        if _RECOVERED:
            return
        records = claim_recoverable_backtest_jobs(_WORKER_ID, limit=100)
        for record in records:
            job = _job_from_record(record)
            if job.status in {"QUEUED", "RUNNING", "TIMEOUT"} and not job.cancel_requested and job.completed_strategies < job.total_strategies:
                _JOBS[job.job_id] = job
                _EXECUTOR.submit(_run_backtest_job, job.job_id)
        _RECOVERED = True


def _persist_job(job: BacktestJob) -> None:
    if job.recovery_owner == _WORKER_ID and job.status in {"QUEUED", "RUNNING", "TIMEOUT"}:
        job.recovery_lease_until = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    update_backtest_job_record(job.job_id, _job_to_record(job))


def _job_to_record(job: BacktestJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "payload": job.payload,
        "strategies": list(job.strategies),
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "current_strategy": job.current_strategy,
        "completed_strategies": job.completed_strategies,
        "total_strategies": job.total_strategies,
        "partial_results": list(job.partial_results),
        "result": job.result,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
        "expected_seconds": job.expected_seconds,
        "recovery_owner": job.recovery_owner,
        "recovery_lease_until": job.recovery_lease_until,
    }


def _job_from_record(record: dict[str, Any]) -> BacktestJob:
    return BacktestJob(
        job_id=str(record["job_id"]),
        payload=dict(record.get("payload") or {}),
        strategies=list(record.get("strategies") or []),
        status=str(record.get("status") or "QUEUED"),
        created_at=str(record.get("created_at") or _utc_now()),
        updated_at=str(record.get("updated_at") or _utc_now()),
        started_at=record.get("started_at"),
        completed_at=record.get("completed_at"),
        current_strategy=record.get("current_strategy"),
        completed_strategies=int(record.get("completed_strategies") or 0),
        total_strategies=int(record.get("total_strategies") or len(record.get("strategies") or [])),
        partial_results=list(record.get("partial_results") or []),
        result=record.get("result"),
        error=record.get("error"),
        cancel_requested=bool(record.get("cancel_requested")),
        expected_seconds=float(record.get("expected_seconds") or 45.0),
        recovery_owner=record.get("recovery_owner"),
        recovery_lease_until=record.get("recovery_lease_until"),
    )


def _comparison_result(job: BacktestJob) -> dict[str, Any]:
    ranked = sorted(
        job.partial_results,
        key=lambda item: (
            float(item.get("metrics", {}).get("sharpe_ratio") or 0),
            float(item.get("metrics", {}).get("net_pnl") or item.get("metrics", {}).get("pnl") or 0),
            -float(item.get("metrics", {}).get("max_drawdown") or 0),
        ),
        reverse=True,
    )
    return {
        "module": "backtesting_comparison",
        "symbol": str(job.payload.get("symbol") or "NIFTY").upper(),
        "runs": list(job.partial_results),
        "ranked": ranked,
        "best_strategy": ranked[0]["strategy"] if ranked else None,
        "updated_at": _utc_now(),
    }


def _job_snapshot(job: BacktestJob) -> dict[str, Any]:
    elapsed = _elapsed_seconds(job)
    remaining = _estimated_remaining_seconds(job, elapsed)
    result = job.result or _comparison_result(job) if job.partial_results else None
    return {
        "job_id": job.job_id,
        "status": job.status,
        "message": _message(job, remaining),
        "created_at": job.created_at,
        "started_at": job.started_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
        "current_strategy": job.current_strategy,
        "completed_strategies": job.completed_strategies,
        "total_strategies": job.total_strategies,
        "progress_pct": round(job.completed_strategies / max(job.total_strategies, 1) * 100, 1),
        "elapsed_seconds": round(elapsed, 1),
        "estimated_remaining_seconds": remaining,
        "partial_results": list(job.partial_results),
        "result": result,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
    }


def _message(job: BacktestJob, remaining: float | None) -> str:
    if job.status == "QUEUED":
        return "Backtest has been queued and will start shortly."
    if job.status == "RUNNING":
        remaining_text = _duration(remaining) if remaining is not None else "calculating"
        return f"Backtest is running. Processed {job.completed_strategies} of {job.total_strategies} strategies. Estimated time remaining: {remaining_text}."
    if job.status == "TIMEOUT":
        return "The backtest exceeded the expected execution time. The job is still running in the background. You can wait for completion or cancel the job."
    if job.status == "COMPLETED":
        return "Backtest completed successfully."
    if job.status == "FAILED":
        return f"Backtest failed. Reason: {job.error or 'Unknown error'}"
    if job.status == "CANCELLED":
        return "Backtest was cancelled."
    return "Backtest status is unavailable."


def _friendly_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()
    if "timeout" in lowered:
        return "Backtesting is taking longer than expected. The analysis is still running. Results will appear automatically when complete."
    if "insufficient" in lowered or "candle" in lowered:
        return "Insufficient historical candle data for the selected backtest."
    if "provider" in lowered or "unavailable" in lowered:
        return "Historical data provider is unavailable."
    if "database" in lowered or "sql" in lowered:
        return "Database timeout while saving or reading backtest results."
    return text


def _estimated_remaining_seconds(job: BacktestJob, elapsed: float) -> float | None:
    if job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
        return 0.0
    if job.completed_strategies <= 0:
        return None
    avg = elapsed / max(job.completed_strategies, 1)
    remaining = max(job.total_strategies - job.completed_strategies, 0) * avg
    return round(remaining, 1)


def _elapsed_seconds(job: BacktestJob) -> float:
    start = _parse_time(job.started_at or job.created_at)
    end = _parse_time(job.completed_at) if job.completed_at else datetime.now(timezone.utc)
    return max(0.0, (end - start).total_seconds())


def _strategy_payload(payload: dict[str, Any], strategy: str) -> dict[str, Any]:
    run_payload = {**payload, "strategy_name": strategy}
    run_payload.pop("strategies", None)
    return run_payload


def _normalize_strategies(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else DEFAULT_STRATEGIES
    strategies = [str(item).strip().lower() for item in raw if str(item).strip()]
    return (strategies or ["amd"])[:12]


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "calculating"
    seconds = max(0, int(round(seconds)))
    minutes, remainder = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
