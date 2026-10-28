"""Invariant tests against real Redis for fixed window rate limiter."""

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
    client = redis.from_url(url, decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_key_always_has_ttl_and_idle_keys_vanish(redis_client: redis.Redis) -> None:
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    rule = Rule(name="ttl_test", limit=5, period=2)
    identity = f"user:ttl_{int(time.time()*1000)}"

    # Perform evaluation
    decision = await service.evaluate(identity, rule)
    assert decision.allowed is True

    # Check key exists in Redis and has a valid TTL > 0
    now = time.time()
    window_id = int(now // rule.period)
    key = service.build_key(identity, rule.name, window_id)

    ttl = await redis_client.ttl(key)
    assert ttl > 0, f"Expected key {key} to have a positive TTL, got {ttl}"
    assert ttl <= rule.period


@pytest.mark.asyncio
async def test_boundary_allows_double_limit_across_window_edge(redis_client: redis.Redis) -> None:
    """Proves the famous fixed window boundary flaw:

    N requests at the very end of window W, plus N requests at the very start
    of window W+1, are ALL allowed within a period shorter than the window.
    """
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    rule = Rule(name="boundary_test", limit=3, period=10)
    identity = f"user:boundary_{int(time.time()*1000)}"

    # Window 0: 3 requests allowed at t=9.9s
    d1 = await service.evaluate(identity, rule, current_time=9.9)
    d2 = await service.evaluate(identity, rule, current_time=9.91)
    d3 = await service.evaluate(identity, rule, current_time=9.92)
    assert d1.allowed and d2.allowed and d3.allowed

    # 4th request in window 0 denied
    d4 = await service.evaluate(identity, rule, current_time=9.93)
    assert d4.allowed is False

    # Window 1 begins at t=10.0s: 3 more requests allowed at t=10.01s
    d5 = await service.evaluate(identity, rule, current_time=10.01)
    d6 = await service.evaluate(identity, rule, current_time=10.02)
    d7 = await service.evaluate(identity, rule, current_time=10.03)
    assert d5.allowed and d6.allowed and d7.allowed

    # Total allowed across 0.15 seconds is 6 (2x the limit of 3!)
    total_allowed = sum([d.allowed for d in [d1, d2, d3, d4, d5, d6, d7]])
    assert total_allowed == 6
