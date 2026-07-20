from fastapi import FastAPI
from agents.audit_agent import run_audit
from reporting.report_generator import generate_report

app = FastAPI(
    title="QuantGrid AI Audit Agent"
)


@app.get("/")
def health():
    return {
        "service": "QuantGrid AI Agent",
        "status": "running"
    }


@app.post("/audit")
def audit(path:str):

    report = run_audit(path)

    report_file = generate_report(report)


    return {
        "status":"completed",
        "report":report,
        "report_file":report_file
    }