"""Unit tests for weighted cost rate limiter service."""

from unittest.mock import AsyncMock

import pytest
from app.repositories.redis_repository import RedisRepository
from app.services.rate_limiter_service import RateLimiterService


@pytest.mark.asyncio
async def test_service_exceeds_burst_status() -> None:
    repo_mock = AsyncMock(spec=RedisRepository)
    # Return code -1 indicates cost > burst
    repo_mock.evaluate.return_value = (-1, 0, 0, 0, 10)

    service = RateLimiterService(repo_mock)
    decision = await service.evaluate("user_1", limit=10, period=10, burst=10, cost=50)

    assert not decision.allowed
    assert decision.status == "exceeds_burst"
    assert decision.retry_after == 0


@pytest.mark.asyncio
async def test_service_fail_open_on_redis_error() -> None:
    repo_mock = AsyncMock(spec=RedisRepository)
    repo_mock.evaluate.side_effect = RuntimeError("Redis connection lost")

    service = RateLimiterService(repo_mock)
    decision = await service.evaluate("user_1", limit=10, period=10, burst=10, cost=2)

    assert decision.allowed
    assert decision.status == "fail_open"
    assert decision.remaining == 10
