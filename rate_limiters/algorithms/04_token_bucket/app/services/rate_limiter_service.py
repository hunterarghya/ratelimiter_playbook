"""Pure rate limiter service for token bucket algorithm."""

from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def evaluate_token_bucket(
        self,
        identity: str,
        rule_name: str,
        capacity: int,
        refill_rate_per_sec: float,
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]: ...


class RateLimiterService:
    def __init__(self, repository: RateLimiterRepository) -> None:
        self.repository = repository

    async def evaluate(
        self,
        identity: str,
        rule: Rule,
        cost: int | None = None,
        now_ms: int = 0,
    ) -> Decision:
        """Evaluates whether a request with the given identity and rule should be allowed."""
        capacity = rule.burst if rule.burst > 0 else rule.limit
        refill_rate = rule.limit / float(rule.period)
        request_cost = cost if cost is not None else rule.cost

        allowed_int, remaining, retry_after, reset, cap = (
            await self.repository.evaluate_token_bucket(
                identity=identity,
                rule_name=rule.name,
                capacity=capacity,
                refill_rate_per_sec=refill_rate,
                cost=request_cost,
                now_ms=now_ms,
            )
        )

        return Decision(
            allowed=bool(allowed_int),
            limit=cap,
            remaining=remaining,
            retry_after=retry_after,
            reset=reset,
            violated_rule=rule.name if not allowed_int else None,
        )
