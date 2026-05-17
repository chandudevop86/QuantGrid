from fastapi import FastAPI

app = FastAPI()

@app.get("/signal")
def signal():
    return {"signals": []}
