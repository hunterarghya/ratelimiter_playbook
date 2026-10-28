"""Demo routes for multi-rule rate limiter."""

import time

from fastapi import APIRouter, Depends

from app.config import settings
from app.controllers.rate_limit_controller import RateLimitController
from app.schemas.rule import Rule

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    rules = [
        Rule(
            name="api_sec",
            limit=settings.rl_sec_limit,
            period=settings.rl_sec_period,
            burst=settings.rl_sec_burst,
        ),
        Rule(
            name="api_hour",
            limit=settings.rl_hour_limit,
            period=settings.rl_hour_period,
            burst=settings.rl_hour_burst,
        ),
    ]

    @router.get("/limited", dependencies=[Depends(controller.require_rate_limit(rules))])
    async def limited_endpoint() -> dict[str, str | float]:
        return {
            "message": "multi-rule request allowed",
            "timestamp": time.time(),
        }

    return router
