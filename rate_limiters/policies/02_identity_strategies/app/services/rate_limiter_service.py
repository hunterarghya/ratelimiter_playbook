"""Pure rate limiter service for evaluating rules across identity targets."""

from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def evaluate_rules(
        self,
        targets: list[tuple[str, Rule]],
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int, str]: ...


class RateLimiterService:
    def __init__(self, repository: RateLimiterRepository) -> None:
        self.repository = repository

    async def evaluate(
        self,
        targets: list[tuple[str, Rule]],
        cost: int = 1,
        now_ms: int = 0,
    ) -> Decision:
        """Evaluates rate limit rules against specified identity targets."""
        if not targets:
            return Decision(
                allowed=True,
                limit=0,
                remaining=0,
                retry_after=0,
                reset=0,
            )

        allowed_int, remaining, retry_after, reset, limit, violated_rule = (
            await self.repository.evaluate_rules(
                targets=targets,
                cost=cost,
                now_ms=now_ms,
            )
        )

        allowed = bool(allowed_int)
        main_identity = targets[0][0]

        return Decision(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after=retry_after,
            reset=reset,
            violated_rule=violated_rule if not allowed else None,
            resolved_identity=main_identity,
        )
