"""Admin endpoints for runtime configuration and rollout mode flipping."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.rate_limiter_service import RateLimiterService

router = APIRouter(prefix="/admin", tags=["admin"])


def create_admin_router(service: RateLimiterService) -> APIRouter:
    @router.get("/mode")
    async def get_mode() -> dict[str, Any]:
        """Returns the currently active rate limiter mode."""
        return {
            "mode": service.mode,
            "allowlist": list(service._allowlist),
        }

    @router.post("/mode")
    async def set_mode(
        mode: str = Query(..., description="Target mode: 'shadow' or 'enforce'"),
    ) -> dict[str, str]:
        """Dynamically switches mode between shadow and enforce with no code change."""
        try:
            service.set_mode(mode)
            return {"status": "ok", "mode": service.mode}
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))

    return router
