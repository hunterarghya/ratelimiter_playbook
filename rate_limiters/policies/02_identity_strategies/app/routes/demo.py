"""Demo routes for identity strategy policies."""

import time

from fastapi import APIRouter, Depends

from app.config import settings
from app.controllers.rate_limit_controller import RateLimitController
from app.schemas.rule import Rule

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    default_rule = Rule(
        name="std",
        limit=settings.rl_limit,
        period=settings.rl_period_seconds,
        burst=settings.rl_burst,
    )
    ip_rule = Rule(name="ip_tier", limit=5, period=10, burst=5)
    user_rule = Rule(name="user_tier", limit=10, period=10, burst=10)
    api_key_rule = Rule(name="key_tier", limit=20, period=10, burst=20)
    tenant_rule = Rule(name="tenant_tier", limit=50, period=10, burst=50)
    endpoint_rule = Rule(name="endpoint_tier", limit=5, period=10, burst=5)
    global_rule = Rule(name="global_tier", limit=100, period=10, burst=100)
    composite_rule = Rule(name="composite_tier", limit=5, period=10, burst=5)

    anon_rule = Rule(name="anon_ip", limit=3, period=10, burst=3)
    auth_rule = Rule(name="auth_user", limit=10, period=10, burst=10)

    @router.get("/limited", dependencies=[Depends(controller.require_user_limit(default_rule))])
    async def limited_endpoint() -> dict[str, str | float]:
        return {"message": "identity limited request allowed", "timestamp": time.time()}

    @router.get("/ip", dependencies=[Depends(controller.require_ip_limit(ip_rule))])
    async def ip_endpoint() -> dict[str, str | float]:
        return {"message": "ip limited request allowed", "timestamp": time.time()}

    @router.get("/user", dependencies=[Depends(controller.require_user_limit(user_rule))])
    async def user_endpoint() -> dict[str, str | float]:
        return {"message": "user limited request allowed", "timestamp": time.time()}

    @router.get("/api-key", dependencies=[Depends(controller.require_api_key_limit(api_key_rule))])
    async def api_key_endpoint() -> dict[str, str | float]:
        return {"message": "api key limited request allowed", "timestamp": time.time()}

    @router.get("/tenant", dependencies=[Depends(controller.require_tenant_limit(tenant_rule))])
    async def tenant_endpoint() -> dict[str, str | float]:
        return {"message": "tenant limited request allowed", "timestamp": time.time()}

    @router.get(
        "/endpoint",
        dependencies=[Depends(controller.require_endpoint_limit(endpoint_rule))],
    )
    async def endpoint_endpoint() -> dict[str, str | float]:
        return {"message": "endpoint limited request allowed", "timestamp": time.time()}

    @router.get("/global", dependencies=[Depends(controller.require_global_limit(global_rule))])
    async def global_endpoint() -> dict[str, str | float]:
        return {"message": "global limited request allowed", "timestamp": time.time()}

    @router.get(
        "/ip-user",
        dependencies=[Depends(controller.require_composite_ip_user_limit(composite_rule))],
    )
    async def ip_user_endpoint() -> dict[str, str | float]:
        return {"message": "composite ip-user request allowed", "timestamp": time.time()}

    @router.get(
        "/transition",
        dependencies=[Depends(controller.require_transition_limit(anon_rule, auth_rule))],
    )
    async def transition_endpoint() -> dict[str, str | float]:
        return {"message": "transition request allowed", "timestamp": time.time()}

    return router
