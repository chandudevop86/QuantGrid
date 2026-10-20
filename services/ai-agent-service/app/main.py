import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from agents.audit_agent import run_audit
from agents.trading_agent import analyze_trading
from reporting.report_generator import generate_report
from audit_security import AuditPathError, resolve_audit_path


logger = logging.getLogger(__name__)


app = FastAPI(
    title="QuantGrid AI Engineering Agent",
    version="1.0"
)



class AuditRequest(BaseModel):

    path: str

    include_llm: bool = True

    agents: list[str] = Field(default_factory=lambda: [
        "architecture",
        "security",
        "devops",
        "trading",
    ])



@app.get("/")
def health():

    return {

        "service":
            "QuantGrid AI Agent",

        "status":
            "running",

        "time":
            datetime.utcnow()

    }



@app.get("/health")
def health_check():

    return {

        "status":
            "healthy"

    }



@app.post("/audit")
def audit(request: AuditRequest):

    try:
        audit_path = str(resolve_audit_path(request.path))
        result = {}


        # Main repository audit

        if "architecture" in request.agents:

            result["architecture"] = run_audit(
                audit_path
            )


        # Trading specific audit

        if "trading" in request.agents:

            result["trading"] = analyze_trading(
                audit_path
            )


        report_file = generate_report(
            result
        )


        return {

            "status":
                "completed",

            "timestamp":
                datetime.utcnow(),

            "report_file":
                report_file,

            "summary":
                build_summary(result),

            "report":
                result

        }


    except AuditPathError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc)}
        ) from exc

    except Exception as exc:
        logger.exception("ai_audit_failed", extra={"error_type": exc.__class__.__name__})
        raise HTTPException(
            status_code=500,
            detail={"code": "audit_failed"}
        ) from exc



def build_summary(report):

    findings = 0

    for agent in report.values():

        if isinstance(agent, dict):

            findings += len(
                agent.get(
                    "findings",
                    []
                )
            )


    return {

        "total_findings":
            findings,

        "agents":
            list(report.keys())

    }