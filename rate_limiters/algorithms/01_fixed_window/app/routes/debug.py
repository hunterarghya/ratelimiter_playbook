"""Debug routes for inspecting rate limiter state in Redis."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.repositories.redis_repository import RedisRepository

router = APIRouter(prefix="/debug", tags=["debug"])


def create_debug_router(repository: RedisRepository) -> APIRouter:
    @router.get("/state")
    async def get_state(identity: str | None = Query(default=None)) -> dict[str, Any]:
        if settings.rl_debug != "1":
            raise HTTPException(status_code=403, detail="Debug endpoint disabled (RL_DEBUG!=1)")

        if identity:
            pattern = f"rl:{{{identity}}}:*"
        else:
            pattern = "rl:*"

        raw_state = await repository.get_state(pattern)
        return {
            "pattern": pattern,
            "keys_found": len(raw_state),
            "state": raw_state,
        }

    return router
