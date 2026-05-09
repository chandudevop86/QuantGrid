from fastapi import FastAPI
import random

app = FastAPI()

@app.get("/signal")
def signal():
    return {
        "signal": random.choice(["BUY","SELL"]),
        "confidence": random.randint(60,95)
    }