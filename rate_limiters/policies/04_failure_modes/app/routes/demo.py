"""Demo routes demonstrating the three failure modes under Redis health vs outage."""

import time

from fastapi import APIRouter, Depends

from app.controllers.rate_limit_controller import RateLimitController

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    @router.get("/limited", dependencies=[Depends(controller.require_mode("open"))])
    async def limited_endpoint() -> dict[str, str | float]:
        return {"message": "standard request allowed", "timestamp": time.time()}

    @router.get("/fail-open", dependencies=[Depends(controller.require_mode("open"))])
    async def fail_open_endpoint() -> dict[str, str | float]:
        return {
            "message": "fail-open request served (availability prioritized)",
            "timestamp": time.time(),
        }

    @router.get("/fail-closed", dependencies=[Depends(controller.require_mode("closed"))])
    async def fail_closed_endpoint() -> dict[str, str | float]:
        return {
            "message": "fail-closed request served (integrity prioritized)",
            "timestamp": time.time(),
        }

    @router.get("/fallback", dependencies=[Depends(controller.require_mode("fallback"))])
    async def fallback_endpoint() -> dict[str, str | float]:
        return {
            "message": "fallback request served (local in-memory limiter active if Redis down)",
            "timestamp": time.time(),
        }

    return router
