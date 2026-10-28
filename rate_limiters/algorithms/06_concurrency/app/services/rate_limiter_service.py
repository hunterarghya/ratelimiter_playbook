"""Pure rate limiter service for concurrency lease management."""

import uuid
from typing import Protocol

from app.schemas.decision import Decision
from app.schemas.rule import Rule


class RateLimiterRepository(Protocol):
    async def acquire_lease(
        self,
        identity: str,
        rule_name: str,
        limit: int,
        lease_id: str,
        lease_ttl_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]: ...

    async def release_lease(
        self,
        identity: str,
        rule_name: str,
        lease_id: str,
    ) -> bool: ...


class RateLimiterService:
    def __init__(self, repository: RateLimiterRepository) -> None:
        self.repository = repository

    async def acquire(
        self,
        identity: str,
        rule: Rule,
        lease_id: str | None = None,
        now_ms: int = 0,
    ) -> Decision:
        """Attempts to acquire a concurrency lease slot under the given rule."""
        assigned_lease_id = lease_id or uuid.uuid4().hex
        lease_ttl_ms = rule.lease_ttl_seconds * 1000

        allowed_int, remaining, retry_after, reset, limit = (
            await self.repository.acquire_lease(
                identity=identity,
                rule_name=rule.name,
                limit=rule.limit,
                lease_id=assigned_lease_id,
                lease_ttl_ms=lease_ttl_ms,
                now_ms=now_ms,
            )
        )

        allowed = bool(allowed_int)
        return Decision(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after=retry_after,
            reset=reset,
            violated_rule=rule.name if not allowed else None,
            lease_id=assigned_lease_id if allowed else None,
        )

    async def release(
        self,
        identity: str,
        rule: Rule,
        lease_id: str,
    ) -> bool:
        """Releases an in-flight lease slot back to the concurrency pool."""
        return await self.repository.release_lease(
            identity=identity,
            rule_name=rule.name,
            lease_id=lease_id,
        )
