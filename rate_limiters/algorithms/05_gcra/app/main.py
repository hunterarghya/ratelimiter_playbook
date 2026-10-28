"""FastAPI application entrypoint for GCRA Rate Limiter."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as redis
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import settings
from app.controllers.rate_limit_controller import RateLimitController
from app.repositories.redis_repository import RedisRepository
from app.routes.debug import create_debug_router
from app.routes.demo import create_demo_router
from app.services.rate_limiter_service import RateLimiterService

redis_client = redis.from_url(settings.redis_url)
repository = RedisRepository(redis_client)
service = RateLimiterService(repository)
controller = RateLimitController(service, limiter_name="gcra")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: Lua script is loaded lazily by register_script on first use
    yield
    # Shutdown
    await redis_client.aclose()


app = FastAPI(
    title="GCRA Rate Limiter",
    lifespan=lifespan,
)

# Attach routes
app.include_router(create_demo_router(controller))
app.include_router(create_debug_router(repository))


@app.get("/health")
async def health() -> dict[str, str]:
    is_up = await repository.ping()
    if is_up:
        return {"status": "ok", "redis": "up"}
    return {"status": "degraded", "redis": "down"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
