"""Pure rate limiter service for fixed window algorithm."""

import time
from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def increment_and_expire(self, key: str, window_seconds: int) -> tuple[int, int]:
        ...


class RateLimiterService:
    """Evaluates fixed window rate limits.

    Clock choice: uses python time.time() (app server clock).
    In multi-server deployments, clocks must be synchronized via NTP (see doc 03 §3 Rule 4).
    """

    def __init__(self, repository: RateLimiterRepository) -> None:
        self.repository = repository

    def build_key(self, identity: str, rule_name: str, window_id: int) -> str:
        """Constructs Redis key with curly braces hash tag enclosing the identity only."""
        return f"rl:{{{identity}}}:{rule_name}:fw:{window_id}"

    async def evaluate(
        self,
        identity: str,
        rule: Rule,
        current_time: float | None = None,
    ) -> Decision:
        now = current_time if current_time is not None else time.time()
        window_id = int(now // rule.period)
        key = self.build_key(identity, rule.name, window_id)

        count, _ = await self.repository.increment_and_expire(key, rule.period)

        allowed = count <= rule.limit
        remaining = max(0, rule.limit - count)
        time_until_reset = max(1, int(((window_id + 1) * rule.period) - now))

        return Decision(
            allowed=allowed,
            retry_after=time_until_reset if not allowed else 0,
            remaining=remaining,
            reset=time_until_reset,
            violated_rule=None if allowed else rule.name,
            limit=rule.limit,
        )
