"""Rate limiter service supporting Enforce, Shadow, and Allowlist modes."""

import logging
from typing import Set

from app.config import settings
from app.observability.metrics import record_decision
from app.repositories.redis_repository import RedisRepository
from app.schemas.decision import Decision

logger = logging.getLogger(__name__)


class RateLimiterService:
    def __init__(self, repository: RedisRepository, initial_mode: str | None = None) -> None:
        self.repository = repository
        self.mode = initial_mode or settings.rl_mode
        self._allowlist: Set[str] = {
            item.strip().lower() for item in settings.rl_allowlist.split(",") if item.strip()
        }

    def set_mode(self, mode: str) -> None:
        """Dynamically change mode between 'shadow' and 'enforce' at runtime."""
        if mode not in ("shadow", "enforce"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'shadow' or 'enforce'.")
        self.mode = mode

    def is_allowlisted(self, identity: str) -> bool:
        """Determines if the given identity bypasses rate limiting."""
        id_clean = identity.strip().lower()
        if id_clean in self._allowlist:
            return True
        for item in self._allowlist:
            if id_clean.startswith(f"{item}:") or id_clean.startswith(f"{item}/"):
                return True
        return False

    async def evaluate(
        self,
        identity: str,
        mode: str | None = None,
        cost: int = 1,
    ) -> Decision:
        effective_mode = mode or self.mode

        # 1. Allowlist check: bypass Redis completely
        if self.is_allowlisted(identity):
            record_decision("shadow_mode", outcome="bypassed", status="allowlist")
            return Decision(
                allowed=True,
                action="bypassed",
                mode="allowlist",
                remaining=settings.rl_burst,
                retry_after=0,
                reset=0,
                limit=settings.rl_limit,
                would_block=False,
                identity=identity,
            )

        # 2. Redis GCRA evaluation
        limit = settings.rl_limit
        period = settings.rl_period_seconds
        burst = settings.rl_burst
        t_ms = (period * 1000.0) / float(limit)
        tau_ms = t_ms * float(burst)

        allowed, remaining, retry_after, reset, limit_ret = await self.repository.evaluate(
            identity=identity,
            rule_name="std",
            t_ms=t_ms,
            tau_ms=tau_ms,
            burst=burst,
            cost=cost,
        )

        is_under_quota = bool(allowed)

        # 3. Apply Mode Policy
        if effective_mode == "enforce":
            if is_under_quota:
                record_decision("shadow_mode", outcome="allowed", status="enforce")
                return Decision(
                    allowed=True,
                    action="allowed",
                    mode="enforce",
                    remaining=remaining,
                    retry_after=0,
                    reset=reset,
                    limit=limit_ret,
                    would_block=False,
                    identity=identity,
                )
            else:
                record_decision("shadow_mode", outcome="denied", status="enforce")
                return Decision(
                    allowed=False,
                    action="denied",
                    mode="enforce",
                    remaining=0,
                    retry_after=retry_after,
                    reset=reset,
                    limit=limit_ret,
                    would_block=True,
                    identity=identity,
                )

        # Shadow mode: Always allow through to upstream, but record would-be denials
        if is_under_quota:
            record_decision("shadow_mode", outcome="allowed", status="shadow")
            return Decision(
                allowed=True,
                action="allowed",
                mode="shadow",
                remaining=remaining,
                retry_after=0,
                reset=reset,
                limit=limit_ret,
                would_block=False,
                identity=identity,
            )
        else:
            logger.warning(
                "SHADOW_DENIED: identity=%s would have been blocked (retry_after=%ds)",
                identity,
                retry_after,
            )
            record_decision("shadow_mode", outcome="shadow_denied", status="shadow")
            return Decision(
                allowed=True,  # Crucial: request is NOT blocked in shadow mode
                action="shadow_denied",
                mode="shadow",
                remaining=0,
                retry_after=retry_after,
                reset=reset,
                limit=limit_ret,
                would_block=True,
                identity=identity,
            )
