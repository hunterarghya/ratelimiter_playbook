"""Service orchestrating weighted rate limiting and cost settlement."""

from app.config import settings
from app.repositories.redis_repository import RedisRepository
from app.schemas.decision import Decision


class RateLimiterService:
    def __init__(self, repository: RedisRepository) -> None:
        self.repository = repository

    async def evaluate(
        self,
        identity: str,
        limit: int,
        period: int,
        burst: int,
        cost: int = 1,
        now_ms: int = 0,
    ) -> Decision:
        try:
            code, remaining, retry_after, reset, limit_ret = await self.repository.evaluate(
                identity=identity,
                limit=limit,
                period=period,
                burst=burst,
                cost=cost,
                now_ms=now_ms,
            )

            if code == -1:
                return Decision(
                    allowed=False,
                    status="exceeds_burst",
                    remaining=0,
                    retry_after=0,
                    reset=0,
                    limit=limit_ret,
                    cost=cost,
                )
            if code == 1:
                return Decision(
                    allowed=True,
                    status="allowed",
                    remaining=remaining,
                    retry_after=0,
                    reset=reset,
                    limit=limit_ret,
                    cost=cost,
                )
            return Decision(
                allowed=False,
                status="rate_limited",
                remaining=remaining,
                retry_after=retry_after,
                reset=reset,
                limit=limit_ret,
                cost=cost,
            )
        except Exception:
            if settings.rl_fail_mode == "open":
                return Decision(
                    allowed=True,
                    status="fail_open",
                    remaining=burst,
                    retry_after=0,
                    reset=0,
                    limit=limit,
                    cost=cost,
                )
            raise

    async def refund(
        self,
        identity: str,
        limit: int,
        period: int,
        burst: int,
        refund_cost: int,
        now_ms: int = 0,
    ) -> tuple[bool, int, int]:
        try:
            success, remaining, new_tat = await self.repository.refund(
                identity=identity,
                limit=limit,
                period=period,
                burst=burst,
                refund_cost=refund_cost,
                now_ms=now_ms,
            )
            return (bool(success), remaining, new_tat)
        except Exception:
            if settings.rl_fail_mode == "open":
                return (True, burst, 0)
            raise
