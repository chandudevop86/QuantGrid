from fastapi import FastAPI
from presentation.api.trading_api import router
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="QuantGrid 🚀")

app.include_router(router)


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("favicon.ico")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)