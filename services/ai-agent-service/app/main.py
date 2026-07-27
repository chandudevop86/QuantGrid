from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

from agents.audit_agent import run_audit
from agents.trading_agent import analyze_trading
from reporting.report_generator import generate_report


app = FastAPI(
    title="QuantGrid AI Engineering Agent",
    version="1.0"
)



class AuditRequest(BaseModel):

    path: str

    include_llm: bool = True

    agents: list[str] = [
        "architecture",
        "security",
        "devops",
        "trading"
    ]



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

        result = {}


        # Main repository audit

        if "architecture" in request.agents:

            result["architecture"] = run_audit(
                request.path
            )


        # Trading specific audit

        if "trading" in request.agents:

            result["trading"] = analyze_trading(
                request.path
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


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )



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