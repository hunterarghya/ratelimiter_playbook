"""Pure rate limiter service for sliding window counter algorithm."""

from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def evaluate_sliding_counter(
        self,
        identity: str,
        rule_name: str,
        limit: int,
        window_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int, int]:
        ...


class RateLimiterService:
    """Evaluates sliding window counter rate limits using two fixed-window counters.

    Clock choice: uses Redis TIME inside Lua by default.
    Explicit timestamps may be passed for deterministic testing.
    """

    def __init__(self, repository: RateLimiterRepository) -> None:
        self.repository = repository

    async def evaluate(
        self,
        identity: str,
        rule: Rule,
        current_time: float | None = None,
    ) -> Decision:
        window_ms = rule.period * 1000
        now_ms = int(current_time * 1000) if current_time is not None else 0

        (
            allowed_int,
            remaining,
            retry_after,
            reset,
            estimated_before,
            estimated_after,
        ) = await self.repository.evaluate_sliding_counter(
            identity=identity,
            rule_name=rule.name,
            limit=rule.limit,
            window_ms=window_ms,
            now_ms=now_ms,
        )

        allowed = bool(allowed_int)

        return Decision(
            allowed=allowed,
            retry_after=retry_after if not allowed else 0,
            remaining=remaining,
            reset=reset,
            violated_rule=None if allowed else rule.name,
            limit=rule.limit,
        )
