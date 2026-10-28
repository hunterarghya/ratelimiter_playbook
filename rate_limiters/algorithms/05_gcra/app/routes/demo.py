"""Demo routes for GCRA rate limiter."""

import time

from fastapi import APIRouter, Depends

from app.config import settings
from app.controllers.rate_limit_controller import RateLimitController
from app.schemas.rule import Rule

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    demo_rule = Rule(
        name="demo_gcra",
        limit=settings.rl_limit,
        period=settings.rl_period_seconds,
        burst=settings.rl_burst,
    )

    @router.get("/limited", dependencies=[Depends(controller.require_rate_limit(demo_rule))])
    async def limited_endpoint() -> dict[str, str | float]:
        return {
            "message": "request succeeded",
            "timestamp": time.time(),
        }

    return router
