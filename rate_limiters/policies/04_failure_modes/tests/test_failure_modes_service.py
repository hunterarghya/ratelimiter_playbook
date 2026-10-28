"""Unit tests for RateLimiterService failure mode behaviors."""

from unittest.mock import AsyncMock

import pytest
from app.repositories.redis_repository import RedisRepository
from app.services.rate_limiter_service import RateLimiterService


@pytest.mark.asyncio
async def test_service_redis_healthy() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.return_value = (1, 4, 0, 0, 5)

    service = RateLimiterService(repo)
    decision = await service.evaluate(identity="user:alice", fail_mode="open")

    assert decision.allowed is True
    assert decision.remaining == 4
    assert decision.source == "redis"


@pytest.mark.asyncio
async def test_service_fail_open_on_redis_error() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.side_effect = ConnectionError("Redis is down")

    service = RateLimiterService(repo)
    decision = await service.evaluate(identity="user:alice", fail_mode="open")

    assert decision.allowed is True
    assert decision.source == "fail_open"


@pytest.mark.asyncio
async def test_service_fail_closed_on_redis_error() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.side_effect = ConnectionError("Redis is down")

    service = RateLimiterService(repo)
    decision = await service.evaluate(identity="user:alice", fail_mode="closed")

    assert decision.allowed is False
    assert decision.source == "fail_closed"
    assert decision.retry_after == 5


@pytest.mark.asyncio
async def test_service_local_fallback_on_redis_error() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.side_effect = TimeoutError("Redis timed out")

    service = RateLimiterService(repo)
    # Drain fallback limiter
    allowed_count = 0
    for _ in range(20):
        decision = await service.evaluate(identity="user:alice", fail_mode="fallback")
        if decision.allowed:
            allowed_count += 1
            assert decision.source == "local_fallback"
        else:
            assert decision.source == "local_fallback"
            break

    assert allowed_count > 0, "Fallback limiter must allow initial requests"


@pytest.mark.asyncio
async def test_service_recovery_after_redis_returns() -> None:
    repo = AsyncMock(spec=RedisRepository)
    repo.evaluate.side_effect = ConnectionError("Redis down")

    service = RateLimiterService(repo)
    # 1. During outage
    d1 = await service.evaluate(identity="user:alice", fail_mode="open")
    assert d1.source == "fail_open"

    # 2. Redis recovers
    repo.evaluate.side_effect = None
    repo.evaluate.return_value = (1, 4, 0, 0, 5)

    d2 = await service.evaluate(identity="user:alice", fail_mode="open")
    assert d2.source == "redis"
    assert d2.allowed is True
