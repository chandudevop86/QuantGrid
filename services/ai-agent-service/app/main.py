from fastapi import FastAPI
from agents.audit_agent import run_audit


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
def audit_project(path:str):

    result = run_audit(path)

    return {
        "status":"completed",
        "report":result
    }