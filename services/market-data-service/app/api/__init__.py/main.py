from fastapi import FastAPI

from app.database.schema import create_tables


app = FastAPI(
    title="QuantGrid Market Data Service",
    version="1.0"
)



@app.on_event("startup")
def startup():

    create_tables()



@app.get("/health")
def health():

    return {

        "service":
        "market-data-service",

        "status":
        "running"

    }