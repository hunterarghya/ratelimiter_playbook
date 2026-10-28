"""Service orchestrating GCRA evaluation with failure mode policies.

Three failure modes:
  - fail_open: Allow request if Redis is down, increment fail_open metric.
  - fail_closed: Block request with 503 if Redis is down.
  - local_fallback: Enforce per-process in-memory limit when Redis is down.
"""

from app.config import settings
from app.observability.metrics import record_decision
from app.repositories.redis_repository import RedisRepository
from app.schemas.decision import Decision
from app.services.local_fallback import LocalFallbackLimiter


class RateLimiterService:
    def __init__(self, repository: RedisRepository) -> None:
        self.repository = repository
        self._fallback = LocalFallbackLimiter(
            limit=settings.rl_limit,
            period=float(settings.rl_period_seconds),
            multiplier=settings.rl_fallback_multiplier,
        )

    async def evaluate(
        self,
        identity: str,
        fail_mode: str = "open",
        cost: int = 1,
    ) -> Decision:
        """Evaluates the rate limit, falling back according to fail_mode on Redis errors."""
        limit = settings.rl_limit
        period = settings.rl_period_seconds
        burst = settings.rl_burst
        t_ms = (period * 1000.0) / float(limit)
        tau_ms = t_ms * float(burst)

        try:
            allowed, remaining, retry_after, reset, limit_ret = await self.repository.evaluate(
                identity=identity,
                rule_name="std",
                t_ms=t_ms,
                tau_ms=tau_ms,
                burst=burst,
                cost=cost,
            )
            outcome = "allowed" if allowed else "denied"
            record_decision("failure_modes", outcome, "redis")
            return Decision(
                allowed=bool(allowed),
                remaining=remaining,
                retry_after=retry_after,
                reset=reset,
                limit=limit_ret,
                source="redis",
            )
        except Exception:
            return self._handle_failure(fail_mode, identity)

    def _handle_failure(self, fail_mode: str, identity: str) -> Decision:
        """Applies the configured failure policy when Redis is unreachable."""
        if fail_mode == "closed":
            record_decision("failure_modes", "denied", "fail_closed")
            return Decision(
                allowed=False,
                remaining=0,
                retry_after=5,
                reset=5,
                limit=settings.rl_limit,
                source="fail_closed",
            )

        if fail_mode == "fallback":
            allowed, remaining = self._fallback.try_acquire()
            outcome = "allowed" if allowed else "denied"
            record_decision("failure_modes", outcome, "local_fallback")
            return Decision(
                allowed=allowed,
                remaining=remaining,
                retry_after=0 if allowed else 1,
                reset=0 if allowed else 1,
                limit=self._fallback.capacity,
                source="local_fallback",
            )

        # Default: fail_open
        record_decision("failure_modes", "allowed", "fail_open")
        return Decision(
            allowed=True,
            remaining=settings.rl_burst,
            retry_after=0,
            reset=0,
            limit=settings.rl_limit,
            source="fail_open",
        )
