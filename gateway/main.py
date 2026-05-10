from fastapi import FastAPI, Request
import httpx

app = FastAPI()

SERVICES = {
    "trading": "http://localhost:8002",
    "strategy": "http://localhost:8003",
}

@app.api_route("/{service}/{path:path}", methods=["GET","POST"])
async def proxy(service: str, path: str, request: Request):
    url = f"{SERVICES[service]}/{path}"

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            request.method,
            url,
            content=await request.body()
        )
    return resp.json()