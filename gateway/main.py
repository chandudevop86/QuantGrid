from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
import httpx

app = FastAPI()

SERVICES = {
    "trading": "http://localhost:8002",
    "strategy": "http://localhost:8003",
}

@app.api_route("/{service}/{path:path}", methods=["GET","POST"])
async def proxy(service: str, path: str, request: Request):
    base_url = SERVICES.get(service)
    if base_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown service: {service}",
        )

    url = f"{base_url}/{path}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                request.method,
                url,
                content=await request.body(),
                params=request.query_params,
                headers={
                    key: value
                    for key, value in request.headers.items()
                    if key.lower() not in {"host", "content-length"}
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Service unavailable: {service}",
        ) from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text}

    return JSONResponse(content=payload, status_code=response.status_code)
