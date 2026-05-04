from fastapi import FastAPI
from presentation.api.trading_api import router

app = FastAPI(title="QuantGrid 🚀")

app.include_router(router)


@app.get("/")
def root():
    return {"status": "running"}