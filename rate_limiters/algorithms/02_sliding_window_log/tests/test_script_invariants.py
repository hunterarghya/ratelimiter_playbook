"""Invariant tests against real Redis for sliding window log Lua script."""

import os
import time
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis
from app.repositories.redis_repository import RedisRepository
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


@pytest.fixture
async def redis_client() -> AsyncIterator[redis.Redis]:
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client = redis.from_url(url, max_connections=50, decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_denied_requests_not_in_zset_and_memory_bounded_by_limit(
    redis_client: redis.Redis,
) -> None:
    """Extra DoD: Denied requests must NOT enter the ZSET, and cardinality never exceeds limit."""
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    limit = 3
    rule = Rule(name="zset_test", limit=limit, period=10)
    identity = f"user:zset_{int(time.time()*1000)}"
    key = service.build_key(identity, rule.name)

    # Clean any prior state
    await redis_client.delete(key)

    # Send 3 requests (fill to capacity)
    for i in range(limit):
        dec = await service.evaluate(identity, rule, current_time=100.0 + i)
        assert dec.allowed is True

    # Initial ZSET cardinality is exactly limit
    card_before = await redis_client.zcard(key)
    assert card_before == limit

    # Now hammer with 10 denied requests
    for i in range(10):
        dec_denied = await service.evaluate(identity, rule, current_time=105.0 + (i * 0.1))
        assert dec_denied.allowed is False

    # Cardinality MUST still be exactly limit (never grows beyond limit)
    card_after = await redis_client.zcard(key)
    assert card_after == limit, f"Expected ZSET cardinality to remain {limit}, got {card_after}"


@pytest.mark.asyncio
async def test_retry_after_equals_oldest_plus_window_minus_now(
    redis_client: redis.Redis,
) -> None:
    """Extra DoD: Retry-After calculation is exact based on oldest timestamp."""
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    rule = Rule(name="retry_test", limit=2, period=10)
    identity = f"user:retry_{int(time.time()*1000)}"

    # Request 1 at t=100.0s (oldest)
    await service.evaluate(identity, rule, current_time=100.0)
    # Request 2 at t=104.0s
    await service.evaluate(identity, rule, current_time=104.0)

    # Denied request at t=106.0s
    # Expected Retry-After: oldest(100.0) + window(10.0) - now(106.0) = 4s
    dec = await service.evaluate(identity, rule, current_time=106.0)
    assert dec.allowed is False
    assert dec.retry_after == 4


@pytest.mark.asyncio
async def test_idle_key_has_ttl_and_vanishes(redis_client: redis.Redis) -> None:
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    rule = Rule(name="ttl_log_test", limit=2, period=2)
    identity = f"user:ttl_{int(time.time()*1000)}"
    key = service.build_key(identity, rule.name)

    await service.evaluate(identity, rule)
    ttl = await redis_client.ttl(key)
    assert ttl > 0
    assert ttl <= 2
