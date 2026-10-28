"""Demo routes for concurrency rate limiter."""

import time

from fastapi import APIRouter, Depends

from app.config import settings
from app.controllers.rate_limit_controller import RateLimitController
from app.schemas.rule import Rule

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    demo_rule = Rule(
        name="demo_concurrency",
        limit=settings.rl_limit,
        lease_ttl_seconds=settings.rl_lease_ttl_seconds,
    )

    @router.get(
        "/limited",
        dependencies=[Depends(controller.require_rate_limit(demo_rule, hold_seconds=0.5))],
    )
    async def limited_endpoint() -> dict[str, str | float]:
        return {
            "message": "concurrency lease granted",
            "timestamp": time.time(),
        }

    return router
