from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

app = FastAPI(title="QuantGrid Auth Service")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    issued_at: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}


@app.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    if not payload.username.strip() or not payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username and password are required",
        )

    return TokenResponse(
        access_token=f"demo-{payload.username}-{uuid4()}",
        issued_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/logout")
def logout():
    return {"status": "ok"}
