"""Demo routes demonstrating Enforce, Shadow, and Allowlist modes."""

import time

from fastapi import APIRouter, Depends

from app.controllers.rate_limit_controller import RateLimitController

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    @router.get("/limited", dependencies=[Depends(controller.require_rate_limit(mode="enforce"))])
    async def limited_endpoint() -> dict[str, str | float]:
        """Standard enforced endpoint matching the universal HTTP test contract."""
        return {"message": "standard request allowed", "timestamp": time.time()}

    @router.get("/shadow", dependencies=[Depends(controller.require_rate_limit(mode="shadow"))])
    async def shadow_endpoint() -> dict[str, str | float]:
        """Shadow mode endpoint: always returns 200, but tracks shadow_denied."""
        return {"message": "shadow request served", "timestamp": time.time()}

    @router.get("/enforce", dependencies=[Depends(controller.require_rate_limit(mode="enforce"))])
    async def enforce_endpoint() -> dict[str, str | float]:
        """Strictly enforced endpoint: returns 429 when quota exhausted."""
        return {"message": "enforced request allowed", "timestamp": time.time()}

    @router.get("/allowlist", dependencies=[Depends(controller.require_rate_limit())])
    async def allowlist_endpoint() -> dict[str, str | float]:
        """Endpoint demonstrating allowlist bypass (trusted callers never hit Redis)."""
        return {"message": "request processed", "timestamp": time.time()}

    @router.get("/dynamic", dependencies=[Depends(controller.require_rate_limit())])
    async def dynamic_endpoint() -> dict[str, str | float]:
        """Dynamic endpoint: respects active global mode (switchable via /admin/mode)."""
        return {"message": "dynamic mode request processed", "timestamp": time.time()}

    return router
