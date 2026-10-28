import redis.asyncio as redis
from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="GCRA Rate Limiter Stub")


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        return {"status": "ok", "redis": "up"}
    except Exception as exc:
        return {"status": "degraded", "redis": f"down: {exc}"}
