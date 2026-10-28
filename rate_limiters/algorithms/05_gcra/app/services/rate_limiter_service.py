"""Pure rate limiter service for GCRA algorithm."""

from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def evaluate_gcra(
        self,
        identity: str,
        rule_name: str,
        t_ms: float,
        tau_ms: float,
        burst: int,
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
        burst = rule.burst if rule.burst > 0 else rule.limit
        request_cost = cost if cost is not None else rule.cost

        t_ms = (rule.period * 1000.0) / float(rule.limit)
        tau_ms = t_ms * float(burst)

        allowed_int, remaining, retry_after, reset, cap = await self.repository.evaluate_gcra(
            identity=identity,
            rule_name=rule.name,
            t_ms=t_ms,
            tau_ms=tau_ms,
            burst=burst,
            cost=request_cost,
            now_ms=now_ms,
        )

        return Decision(
            allowed=bool(allowed_int),
            limit=cap,
            remaining=remaining,
            retry_after=retry_after,
            reset=reset,
            violated_rule=rule.name if not allowed_int else None,
        )
