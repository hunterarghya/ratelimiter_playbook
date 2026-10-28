"""Unit tests verifying allowlist behavior and Redis bypass."""

from unittest.mock import AsyncMock

import pytest
from app.repositories.redis_repository import RedisRepository
from app.services.rate_limiter_service import RateLimiterService


def test_allowlist_matching_logic() -> None:
    repo = AsyncMock(spec=RedisRepository)
    service = RateLimiterService(repo)

    # Direct match from config (user:admin, ip:127.0.0.1, system)
    assert service.is_allowlisted("user:admin") is True
    assert service.is_allowlisted("ip:127.0.0.1") is True
    assert service.is_allowlisted("system") is True

    # Prefix match
    assert service.is_allowlisted("system:cron") is True

    # Unknown identity
    assert service.is_allowlisted("user:bob") is False
    assert service.is_allowlisted("ip:192.168.1.50") is False


@pytest.mark.asyncio
async def test_allowlisted_identity_never_calls_redis() -> None:
    repo = AsyncMock(spec=RedisRepository)
    service = RateLimiterService(repo)

    decision = await service.evaluate("user:admin")

    assert decision.allowed is True
    assert decision.action == "bypassed"
    assert decision.mode == "allowlist"
    assert decision.would_block is False

    # Verify Redis repository was NEVER invoked
    repo.evaluate.assert_not_called()
