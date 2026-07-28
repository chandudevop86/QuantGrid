from fastapi import FastAPI

from app.database.schema import create_tables

from app.scheduler.jobs import start_scheduler

from app.api.routes import router


app = FastAPI(

    title="QuantGrid Market Data Service",

    version="1.0.0"

)


app.include_router(router)



@app.on_event("startup")
def startup():

    create_tables()

    start_scheduler()



@app.get("/health")
def health():

    return {

        "service": "market-data-service",

        "status": "running"

    }