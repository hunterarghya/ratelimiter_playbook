"""Invariant tests against real Redis for sliding window counter Lua script."""

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
async def test_denied_requests_do_not_increment_counter(
    redis_client: redis.Redis,
) -> None:
    """Extra DoD: Denied requests must NOT increment the current window counter."""
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    limit = 3
    rule = Rule(name="incr_test", limit=limit, period=10)
    identity = f"user:incr_{int(time.time()*1000)}"

    # Fill to capacity
    for i in range(limit):
        dec = await service.evaluate(identity, rule, current_time=100.0 + i * 0.001)
        assert dec.allowed is True

    # Hammer with 10 denied requests
    for i in range(10):
        dec = await service.evaluate(identity, rule, current_time=100.5 + i * 0.001)
        assert dec.allowed is False

    # Verify the counter key value is still exactly `limit`
    window_ms = rule.period * 1000
    window_num = 100000 // window_ms
    curr_key = f"rl:{{{identity}}}:{rule.name}:swc:{window_num}"
    raw_val = await redis_client.get(curr_key)
    counter_val = int(raw_val) if raw_val else 0
    assert counter_val == limit, f"Counter should be {limit}, got {counter_val}"


@pytest.mark.asyncio
async def test_idle_key_has_ttl(redis_client: redis.Redis) -> None:
    """Every key gets a TTL; idle keys vanish."""
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    rule = Rule(name="ttl_counter_test", limit=5, period=2)
    identity = f"user:ttl_{int(time.time()*1000)}"

    await service.evaluate(identity, rule, current_time=100.0)

    # Find the counter key
    window_ms = rule.period * 1000
    window_num = 100000 // window_ms
    curr_key = f"rl:{{{identity}}}:{rule.name}:swc:{window_num}"
    ttl = await redis_client.ttl(curr_key)
    assert ttl > 0, f"Key {curr_key} should have a positive TTL, got {ttl}"
    assert ttl <= 4, f"TTL should be <= 2*period(2)=4s, got {ttl}"


@pytest.mark.asyncio
async def test_blending_with_previous_window(redis_client: redis.Redis) -> None:
    """Verifies the approximation formula blends previous and current windows."""
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    rule = Rule(name="blend_test", limit=10, period=10)
    identity = f"user:blend_{int(time.time()*1000)}"

    # Fill previous window with 8 requests
    # Window starts at t=0, window #0
    for i in range(8):
        dec = await service.evaluate(identity, rule, current_time=1.0 + i * 0.001)
        assert dec.allowed is True

    # Now jump to 50% into the next window: t=15.0s -> window #1, elapsed 50%
    # weight for prev = 0.5
    # estimated = floor(8 * 0.5 + 0) = 4
    # So we should be able to make 6 more requests (4+6=10)
    fixed_time_w2 = 15.0  # Fixed timestamp: exactly 50% into window #1
    for i in range(6):
        dec = await service.evaluate(identity, rule, current_time=fixed_time_w2)
        assert dec.allowed is True, f"Request {i + 1} in new window should be allowed"

    # 7th request should be denied (floor(8*0.5 + 6) = 10 >= 10)
    dec = await service.evaluate(identity, rule, current_time=fixed_time_w2)
    assert dec.allowed is False, "Should be denied after estimated reaches limit"
