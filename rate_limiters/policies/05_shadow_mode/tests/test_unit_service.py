"""Unit tests for RateLimiterService in Shadow and Enforce modes."""

from unittest.mock import AsyncMock

import pytest
from app.repositories.redis_repository import RedisRepository
from app.services.rate_limiter_service import RateLimiterService


@pytest.mark.asyncio
async def test_shadow_mode_allows_request_and_flags_shadow_denied() -> None:
    repo = AsyncMock(spec=RedisRepository)
    # Simulate Redis GCRA returning allowed=0 (quota exceeded)
    repo.evaluate.return_value = (0, 0, 5, 5, 5)

    service = RateLimiterService(repo, initial_mode="shadow")
    decision = await service.evaluate("user:alice")

    # In shadow mode, the client request is STILL allowed!
    assert decision.allowed is True
    assert decision.action == "shadow_denied"
    assert decision.mode == "shadow"
    assert decision.would_block is True
    assert decision.retry_after == 5


@pytest.mark.asyncio
async def test_enforce_mode_blocks_request_on_quota_exceeded() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.return_value = (0, 0, 5, 5, 5)

    service = RateLimiterService(repo, initial_mode="enforce")
    decision = await service.evaluate("user:alice")

    # In enforce mode, the request is BLOCKED
    assert decision.allowed is False
    assert decision.action == "denied"
    assert decision.mode == "enforce"
    assert decision.would_block is True
    assert decision.retry_after == 5


@pytest.mark.asyncio
async def test_runtime_mode_switch_flips_behavior() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.return_value = (0, 0, 5, 5, 5)

    service = RateLimiterService(repo, initial_mode="shadow")

    # 1. Under shadow mode: allowed
    d1 = await service.evaluate("user:alice")
    assert d1.allowed is True
    assert d1.action == "shadow_denied"

    # 2. Switch mode to enforce at runtime
    service.set_mode("enforce")
    d2 = await service.evaluate("user:alice")
    assert d2.allowed is False
    assert d2.action == "denied"
