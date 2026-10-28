"""Pure rate limiter service for sliding window log algorithm."""

from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def evaluate_sliding_log(
        self,
        key: str,
        limit: int,
        window_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int]:
        ...


class RateLimiterService:
    """Evaluates sliding window log rate limits via Redis ZSETs.

    Clock choice: uses Redis TIME inside Lua by default.
    Explicit timestamps may be passed for deterministic testing.
    """

    def __init__(self, repository: RateLimiterRepository) -> None:
        self.repository = repository

    def build_key(self, identity: str, rule_name: str) -> str:
        """Constructs Redis key with curly braces hash tag enclosing the identity only."""
        return f"rl:{{{identity}}}:{rule_name}:log"

    async def evaluate(
        self,
        identity: str,
        rule: Rule,
        current_time: float | None = None,
    ) -> Decision:
        key = self.build_key(identity, rule.name)
        window_ms = rule.period * 1000
        now_ms = int(current_time * 1000) if current_time is not None else 0

        allowed_int, remaining, retry_after, reset = await self.repository.evaluate_sliding_log(
            key=key,
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
