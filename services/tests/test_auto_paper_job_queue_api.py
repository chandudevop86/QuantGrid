from __future__ import annotations

import asyncio
from types import SimpleNamespace

from Backend.presentation.api import execution


def test_auto_paper_jobs_enqueue_durable_live_analysis_jobs(monkeypatch):
    queued_calls = []

    def fake_enqueue(job_type, payload, *, metadata=None, job_id=None):
        queued_calls.append(
            {
                "job_type": job_type,
                "payload": payload,
                "metadata": metadata,
                "job_id": job_id,
            }
        )
        return {
            "job_id": f"job-{len(queued_calls)}",
            "job_type": job_type,
            "status": "queued",
            **(metadata or {}),
        }

    monkeypatch.setattr(execution, "enqueue_job", fake_enqueue)

    payload = execution.AutoPaperExecutionRequest(
        symbol="NIFTY",
        interval="1m",
        period="1d",
        capital=100000,
        risk_pct=2,
        rr_ratio=2,
        strategies=["breakout", "mtf"],
    )
    access = SimpleNamespace(
        can=lambda feature: feature == "paper_trade.automated",
        snapshot={"plan_code": "pro"},
    )

    result = asyncio.run(
        execution.enqueue_auto_paper_order(
            payload,
            request=None,
            actor=None,
            access=access,
            execution_mode="paper",
            engine=None,
        )
    )

    assert result["status"] == "accepted"
    assert result["job_count"] == 2
    assert [call["job_type"] for call in queued_calls] == ["live-analysis", "live-analysis"]
    assert [call["payload"]["strategy"] for call in queued_calls] == ["breakout", "mtf"]
    assert all(call["payload"]["auto_trade"] is True for call in queued_calls)
    assert all(call["payload"]["execution_mode"] == "paper" for call in queued_calls)
    assert all(call["metadata"]["execution_mode"] == "paper" for call in queued_calls)
    assert [job["job_id"] for job in result["jobs"]] == ["job-1", "job-2"]


def test_auto_paper_jobs_default_to_supported_scan_strategies(monkeypatch):
    queued_strategies = []

    def fake_enqueue(job_type, payload, *, metadata=None, job_id=None):
        queued_strategies.append(payload["strategy"])
        return {"job_id": f"job-{len(queued_strategies)}", "status": "queued"}

    monkeypatch.setattr(execution, "enqueue_job", fake_enqueue)

    payload = execution.AutoPaperExecutionRequest(symbol="NIFTY")
    access = SimpleNamespace(
        can=lambda feature: feature == "paper_trade.automated",
        snapshot={"plan_code": "pro"},
    )

    result = asyncio.run(
        execution.enqueue_auto_paper_order(
            payload,
            request=None,
            actor=None,
            access=access,
            execution_mode="paper",
            engine=None,
        )
    )

    assert queued_strategies == execution.AUTO_SCAN_STRATEGIES
    assert result["job_count"] == len(execution.AUTO_SCAN_STRATEGIES)
